# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response # Importar Response
import werkzeug # Para exceções HTTP se necessário

_logger = logging.getLogger(__name__)

class PesquisaAiiaWebhook(http.Controller):

    # MUDANÇA AQUI: type='http' em vez de 'json'
    @http.route('/pesquisa_aiia/webhook', type='http', auth='public', methods=['POST'], csrf=False)
    def handle_webhook_http(self, **kwargs): # **kwargs pode ser útil com type='http' se dados vierem na URL
        """
        Recebe os dados do N8N via POST, lê o corpo manualmente como JSON.
        """
        webhook_data = None
        try:
            # 1. Ler o corpo raw da requisição
            raw_body = request.httprequest.data
            if not raw_body:
                 _logger.warning("Webhook Pesquisa AIIA: Corpo da requisição vazio recebido.")
                 # Retornar erro como JSON Response
                 return Response(json.dumps({'status': 'error', 'message': 'Corpo da requisição vazio'}),
                                 content_type='application/json', status=400)

            # 2. Decodificar para string (assumindo UTF-8)
            body_str = raw_body.decode('utf-8')
            _logger.info("Webhook Pesquisa AIIA: Corpo Raw Recebido (type='http'): %s", body_str)

            # 3. Parsear a string como JSON
            webhook_data = json.loads(body_str)

        except json.JSONDecodeError as e:
            _logger.error("Webhook Pesquisa AIIA: Erro ao decodificar JSON manualmente - %s. Corpo recebido: %s", str(e), body_str[:500]) # Loga parte do corpo
            return Response(json.dumps({'status': 'error', 'message': f'Erro ao decodificar JSON: {str(e)}'}),
                            content_type='application/json', status=400) # Bad Request
        except Exception as e:
            # Captura outros erros (ex: decode error)
            _logger.exception("Webhook Pesquisa AIIA: Erro inesperado ao processar corpo da requisição - %s", str(e))
            return Response(json.dumps({'status': 'error', 'message': f'Erro ao processar corpo: {str(e)}'}),
                            content_type='application/json', status=500) # Internal Server Error

        _logger.info("Webhook Pesquisa AIIA Recebido (processado manualmente): %s", json.dumps(webhook_data))

        # --- Validação de Segurança (Opcional) ---
        # ... (código de validação do segredo permanece o mesmo, usando request.httprequest.headers)
        secret = request.env['ir.config_parameter'].sudo().get_param('pesquisa_aiia.webhook_secret')
        received_secret = request.httprequest.headers.get('X-N8N-Signature') # Exemplo de header
        if secret and received_secret != secret:
             _logger.warning("Webhook Pesquisa AIIA: Segredo inválido recebido.")
             return Response(json.dumps({'status': 'error', 'message': 'Unauthorized'}),
                             content_type='application/json', status=401) # Unauthorized

        # --- Validação dos Dados ---
        required_fields = ['nome_empresa', 'contato_telefonico', 'email', 'endereco', 'resumo_atividade']
        if not isinstance(webhook_data, dict) or not all(field in webhook_data for field in required_fields):
            _logger.error("Webhook Pesquisa AIIA: Dados incompletos ou formato inválido - %s", webhook_data)
            return Response(json.dumps({'status': 'error', 'message': 'Dados incompletos ou formato inválido'}),
                            content_type='application/json', status=400) # Bad Request

        # --- Criação do Lead ---
        try:
            lead_vals = {
                'name': webhook_data.get('nome_empresa'),
                'phone': webhook_data.get('contato_telefonico'),
                'email': webhook_data.get('email'),
                'address': webhook_data.get('endereco'),
                'activity_summary': webhook_data.get('resumo_atividade'),
            }
            # Usar sudo() porque auth='public'
            new_lead = request.env['pesquisa_aiia.lead'].sudo().create(lead_vals)
            _logger.info("Webhook Pesquisa AIIA: Lead criado com ID: %s", new_lead.id)

            # Retornar sucesso como JSON Response
            response_data = {'status': 'success', 'lead_id': new_lead.id}
            return Response(json.dumps(response_data), content_type='application/json', status=200) # OK

        except Exception as e:
            _logger.exception("Webhook Pesquisa AIIA: Erro ao criar lead - %s", str(e))
            request.env.cr.rollback()
            # Retornar erro interno como JSON Response
            return Response(json.dumps({'status': 'error', 'message': f'Erro interno do servidor: {str(e)}'}),
                            content_type='application/json', status=500) # Internal Server Error