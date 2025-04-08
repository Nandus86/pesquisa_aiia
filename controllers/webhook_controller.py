# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

class PesquisaAiiaWebhook(http.Controller):

    @http.route('/pesquisa_aiia/webhook', type='json', auth='public', methods=['POST'], csrf=False)
    def handle_webhook(self, **kwargs):
        """
        Recebe os dados do N8N via JSON POST.
        """
        webhook_data = request.jsonrequest
        _logger.info("Webhook Pesquisa AIIA Recebido: %s", json.dumps(webhook_data))

        # --- Validação de Segurança (Opcional, mas recomendado) ---
        secret = request.env['ir.config_parameter'].sudo().get_param('pesquisa_aiia.webhook_secret')
        # Exemplo: Verificar um header ou um campo no JSON
        # received_secret = request.httprequest.headers.get('X-N8N-Signature')
        # if secret and received_secret != secret:
        #     _logger.warning("Webhook Pesquisa AIIA: Segredo inválido recebido.")
        #     return Response("Unauthorized", status=401)

        # --- Validação dos Dados ---
        required_fields = ['nome_empresa', 'contato_telefonico', 'email', 'endereco', 'resumo_atividade']
        if not webhook_data or not all(field in webhook_data for field in required_fields):
            _logger.error("Webhook Pesquisa AIIA: Dados incompletos recebidos - %s", webhook_data)
            # Retornar um erro JSON para o N8N poder tratar
            return {'status': 'error', 'message': 'Dados incompletos'}

        # --- Criação do Lead ---
        try:
            # Usar sudo() porque o usuário 'public' não tem permissão de escrita
            # Considerar criar um usuário API específico para mais segurança
            lead_vals = {
                'name': webhook_data.get('nome_empresa'),
                'phone': webhook_data.get('contato_telefonico'),
                'email': webhook_data.get('email'),
                'address': webhook_data.get('endereco'),
                'activity_summary': webhook_data.get('resumo_atividade'),
                # 'message_text' e 'use_default_message' ficam com os defaults do modelo
            }
            new_lead = request.env['pesquisa_aiia.lead'].sudo().create(lead_vals)
            _logger.info("Webhook Pesquisa AIIA: Lead criado com ID: %s", new_lead.id)

            # Retornar sucesso para o N8N
            return {'status': 'success', 'lead_id': new_lead.id}

        except Exception as e:
            _logger.exception("Webhook Pesquisa AIIA: Erro ao criar lead - %s", str(e))
            # Retornar erro genérico
            # O N8N pode precisar de um status HTTP 500 também
            request.env.cr.rollback() # Desfaz a transação em caso de erro
            # Considerar retornar Response("Internal Server Error", status=500)
            return {'status': 'error', 'message': f'Erro interno do servidor: {str(e)}'}