# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response
import werkzeug

_logger = logging.getLogger(__name__)

class PesquisaAiiaWebhook(http.Controller):

    @http.route('/pesquisa_aiia/webhook', type='http', auth='public', methods=['POST'], csrf=False)
    def handle_webhook_http(self, **kwargs):
        """
        Recebe uma LISTA de dados de leads do N8N via POST, lê o corpo manualmente como JSON.
        """
        all_webhook_data = None
        try:
            raw_body = request.httprequest.data
            if not raw_body:
                _logger.warning("Webhook Pesquisa AIIA: Corpo da requisição vazio recebido.")
                return Response(json.dumps({'status': 'error', 'message': 'Corpo da requisição vazio'}),
                                content_type='application/json', status=400)

            body_str = raw_body.decode('utf-8')
            _logger.info("Webhook Pesquisa AIIA: Corpo Raw Recebido (esperando lista): %s", body_str[:1000]) # Loga parte do corpo

            all_webhook_data = json.loads(body_str)

            # *** VALIDAÇÃO: Espera-se uma LISTA ***
            if not isinstance(all_webhook_data, list):
                 _logger.error("Webhook Pesquisa AIIA: Formato inválido - Esperava uma lista, recebeu %s.", type(all_webhook_data).__name__)
                 return Response(json.dumps({'status': 'error', 'message': 'Formato inválido. Esperava uma lista de leads.'}),
                                 content_type='application/json', status=400)

        except json.JSONDecodeError as e:
            _logger.error("Webhook Pesquisa AIIA: Erro ao decodificar JSON - %s. Corpo: %s", str(e), body_str[:500])
            return Response(json.dumps({'status': 'error', 'message': f'Erro ao decodificar JSON: {str(e)}'}),
                            content_type='application/json', status=400)
        except Exception as e:
            _logger.exception("Webhook Pesquisa AIIA: Erro inesperado ao processar corpo da requisição - %s", str(e))
            return Response(json.dumps({'status': 'error', 'message': f'Erro ao processar corpo: {str(e)}'}),
                            content_type='application/json', status=500)

        _logger.info("Webhook Pesquisa AIIA Recebido: %d leads na lista.", len(all_webhook_data))

        # --- Validação de Segurança (Opcional) ---
        secret = request.env['ir.config_parameter'].sudo().get_param('pesquisa_aiia.webhook_secret')
        received_secret = request.httprequest.headers.get('X-N8N-Signature')
        if secret and received_secret != secret:
            _logger.warning("Webhook Pesquisa AIIA: Segredo inválido recebido.")
            return Response(json.dumps({'status': 'error', 'message': 'Unauthorized'}),
                            content_type='application/json', status=401)

        # --- Processamento e Criação dos Leads (Iterando a Lista) ---
        leads_criados_count = 0
        leads_erros_count = 0
        erros_detalhes = []
        required_fields = ['search_id', 'nome_empresa', 'contato_telefonico', 'email', 'endereco', 'resumo_atividade']

        PesquisaSearch = request.env['pesquisa_aiia.search'].sudo()
        PesquisaLead = request.env['pesquisa_aiia.lead'].sudo()

        # Verificar search_ids únicos para buscar em lote (otimização)
        search_ids_na_lista = {item.get('search_id') for item in all_webhook_data if isinstance(item.get('search_id'), int)}
        existing_searches = PesquisaSearch.browse(list(search_ids_na_lista))
        existing_search_map = {s.id: s for s in existing_searches}

        for index, lead_data in enumerate(all_webhook_data):
            try:
                # --- Validação dos Dados de cada lead na lista ---
                search_id = lead_data.get('search_id') if isinstance(lead_data, dict) else None

                if not isinstance(lead_data, dict) \
                   or not all(field in lead_data for field in required_fields) \
                   or not isinstance(search_id, int):
                    _logger.error("Webhook AIIA Lead (item %d): Dados incompletos/inválidos - %s", index, lead_data)
                    erros_detalhes.append({'index': index, 'error': 'Dados incompletos ou formato inválido (search_id obrigatório e inteiro)'})
                    leads_erros_count += 1
                    continue # Pula para o próximo item da lista

                # Verificar se a pesquisa existe (usando o mapa pré-buscado)
                search_record = existing_search_map.get(search_id)
                if not search_record:
                     _logger.warning(f"Webhook AIIA Lead (item %d): Search ID {search_id} não encontrado ao tentar criar lead.", index)
                     # Decisão: Continuar ou falhar? Vamos continuar e logar.
                     # Pode ser que a pesquisa tenha sido apagada entre o envio e o recebimento.

                # Criar o lead
                lead_vals = {
                    'search_id': search_id,
                    'name': lead_data.get('nome_empresa'),
                    'phone': lead_data.get('contato_telefonico'),
                    'email': lead_data.get('email'),
                    'address': lead_data.get('endereco'),
                    'activity_summary': lead_data.get('resumo_atividade'),
                }
                new_lead = PesquisaLead.create(lead_vals)
                _logger.info(f"Webhook AIIA Lead (item %d): Lead {new_lead.id} criado e vinculado à pesquisa {search_id}.")
                leads_criados_count += 1

            except Exception as e:
                _logger.exception("Webhook Pesquisa AIIA (item %d): Erro ao criar lead - %s. Dados: %s", index, str(e), lead_data)
                leads_erros_count += 1
                erros_detalhes.append({'index': index, 'error': f'Erro interno: {str(e)}'})
                # Importante: Não fazer rollback aqui para não desfazer leads já criados com sucesso na mesma requisição
                # request.env.cr.rollback() # <<-- EVITAR DENTRO DO LOOP SE QUISER PROCESSAMENTO PARCIAL

        # --- Resposta Final ---
        response_status = 200 if leads_erros_count == 0 else 207 # 200 OK ou 207 Multi-Status
        response_data = {
            'status': 'success' if leads_erros_count == 0 else 'partial_success',
            'leads_processed': len(all_webhook_data),
            'leads_created': leads_criados_count,
            'leads_errors': leads_erros_count,
        }
        if erros_detalhes:
             response_data['errors_details'] = erros_detalhes

        return Response(json.dumps(response_data), content_type='application/json', status=response_status)