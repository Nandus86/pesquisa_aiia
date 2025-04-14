# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class PesquisaAiiaScrapeWizard(models.TransientModel):
    _name = 'pesquisa_aiia.scrape.wizard'
    _description = 'Wizard para Iniciar Pesquisa AIIA'

    search_query = fields.Text(string='Termo de Pesquisa', required=True, help="Digite o que você deseja pesquisar (ex: 'Salões de beleza em Curitiba', 'Restaurantes veganos SP')")

    def action_trigger_scrape(self):
        self.ensure_one()
        if not self.search_query:
            raise ValidationError(_("Por favor, insira um termo de pesquisa."))

        search_record = self.env['pesquisa_aiia.search'].create({
            'search_query': self.search_query,
            'user_id': self.env.user.id,
            'status': 'new', # Status inicial
        })
        search_id = search_record.id

        # Obter a URL do webhook de trigger da configuração
        config_params = self.env['ir.config_parameter'].sudo()
        n8n_trigger_url = config_params.get_param('pesquisa_aiia.n8n_scrape_trigger_url')

        if not n8n_trigger_url:
            raise UserError(_("A 'URL Webhook N8N (Iniciar Scraping)' não está configurada. Vá em Configurações -> Pesquisa AIIA para defini-la."))

        # Preparar o payload para enviar ao N8N
        payload = {
            'search_id': search_id,
            'query': self.search_query,
            'odoo_user_id': self.env.user.id, # Envia ID do usuário que solicitou
            'odoo_user_name': self.env.user.name # Envia nome do usuário
            # Você pode adicionar mais informações se o N8N precisar
        }

        headers = {'Content-Type': 'application/json'}

        _logger.info(f"Iniciando scraping AIIA (Search ID: {search_id}). Enviando query '{self.search_query}' para {n8n_trigger_url}")
        # Atualiza status no registro de pesquisa
        search_record.write({'status': 'processing'})

        try:
            response = requests.post(n8n_trigger_url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            _logger.info(f"Solicitação de scraping (Search ID: {search_id}) enviada com sucesso para N8N.")

            # Mostrar notificação de sucesso e fechar o wizard
            self.env.user.notify_success(
                message=_("Pesquisa por '%s' iniciada. Os resultados aparecerão em breve.", self.search_query)
            )
            # Fechar o wizard - O usuário ainda estará na lista de pesquisas
            return {'type': 'ir.actions.act_window_close'}

        except requests.exceptions.Timeout:
            _logger.error(f"Timeout ao enviar solicitação (Search ID: {search_id}): {n8n_trigger_url}")
            search_record.write({'status': 'error', 'error_message': f"Timeout N8N: {n8n_trigger_url}"})
            raise UserError(_("O serviço N8N demorou muito para confirmar o recebimento (Timeout)."))
        except requests.exceptions.RequestException as e:
            _logger.error(f"Erro ao enviar solicitação (Search ID: {search_id}): {e}")
            error_details = str(e)
            if hasattr(e, 'response') and e.response is not None:
                 try: error_details = e.response.json()
                 except json.JSONDecodeError: error_details = e.response.text[:500]
            search_record.write({'status': 'error', 'error_message': f"Erro N8N: {error_details}"})
            raise UserError(_("Erro ao comunicar com o N8N para iniciar a pesquisa: %s", error_details))
        except Exception as e:
             _logger.exception(f"Erro inesperado (Search ID: {search_id}):")
             search_record.write({'status': 'error', 'error_message': f"Erro inesperado: {str(e)}"})
             raise UserError(_("Ocorreu um erro inesperado: %s", str(e)))