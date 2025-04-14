# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response
import werkzeug

_logger = logging.getLogger(__name__)

class AiiaSearchUpdate(http.Controller):

    def _validate_request(self):
        """Valida o segredo do webhook de update, se configurado."""
        secret = request.env['ir.config_parameter'].sudo().get_param('pesquisa_aiia.aiia_odoo_update_secret') # Usa o novo segredo
        if secret:
            received_secret = request.httprequest.headers.get('X-N8N-Odoo-Update-Secret') # Header específico
            if not received_secret or received_secret != secret:
                _logger.warning("AI Search Update: Chamada não autorizada (segredo inválido/ausente).")
                raise werkzeug.exceptions.Unauthorized("Segredo inválido.")
        return True

    @http.route('/pesquisa_aiia/update_search', type='http', auth='public', methods=['POST'], csrf=False)
    def update_search_status(self, **kwargs):
        """ Recebe atualização do N8N sobre status e token da próxima página."""
        try:
            self._validate_request()
        except werkzeug.exceptions.Unauthorized as e:
             return Response(json.dumps({'status': 'error', 'message': str(e)}),
                             content_type='application/json', status=401)

        webhook_data = None
        try:
            raw_body = request.httprequest.data
            if not raw_body:
                 _logger.warning("AI Search Update: Corpo vazio recebido.")
                 return Response(json.dumps({'status': 'error', 'message': 'Corpo vazio'}),
                                 content_type='application/json', status=400)
            body_str = raw_body.decode('utf-8')
            _logger.info("AI Search Update: Corpo Raw Recebido: %s", body_str)
            webhook_data = json.loads(body_str)

        except Exception as e:
            _logger.error("AI Search Update: Erro ao processar corpo: %s", str(e))
            return Response(json.dumps({'status': 'error', 'message': f'Erro corpo: {str(e)}'}),
                            content_type='application/json', status=400)

        _logger.info("AI Search Update: Dados recebidos: %s", json.dumps(webhook_data))

        # Validação do payload
        search_id = webhook_data.get('search_id')
        next_page_token = webhook_data.get('next_page_token') # Pode ser None ou "" se for a última página
        status = webhook_data.get('status') # 'pending_next', 'completed', 'error'
        error_message = webhook_data.get('error_message') # Opcional

        valid_statuses = ['pending_next', 'completed', 'error']

        if not search_id or not isinstance(search_id, int) or status not in valid_statuses:
            _logger.error("AI Search Update: Payload inválido - %s", webhook_data)
            return Response(json.dumps({'status': 'error', 'message': 'Payload inválido (search_id ou status ausente/inválido)'}),
                            content_type='application/json', status=400)

        # Atualizar o registro da pesquisa
        search_record = request.env['pesquisa_aiia.search'].sudo().browse(search_id)
        if not search_record.exists():
            _logger.error(f"AI Search Update: Search ID {search_id} não encontrado.")
            return Response(json.dumps({'status': 'error', 'message': f'Search ID {search_id} não encontrado'}),
                            content_type='application/json', status=404)

        try:
            update_vals = {
                'status': status,
                # Atualiza o token apenas se um novo foi fornecido (pode ser None/vazio para indicar fim)
                'next_page_token': next_page_token,
                'error_message': error_message if status == 'error' else False,
            }
            search_record.write(update_vals)
            _logger.info(f"AI Search Update: Pesquisa {search_id} atualizada para status '{status}'.")
            return Response(json.dumps({'status': 'success'}), content_type='application/json', status=200)

        except Exception as e:
            _logger.exception(f"AI Search Update: Erro ao atualizar pesquisa {search_id}: {e}")
            request.env.cr.rollback()
            return Response(json.dumps({'status': 'error', 'message': f'Erro interno ao atualizar pesquisa: {str(e)}'}),
                            content_type='application/json', status=500)