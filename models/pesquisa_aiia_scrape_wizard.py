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

        # Obter a URL do webhook de trigger da configuração
        config_params = self.env['ir.config_parameter'].sudo()
        n8n_trigger_url = config_params.get_param('pesquisa_aiia.n8n_scrape_trigger_url')

        if not n8n_trigger_url:
            raise UserError(_("A 'URL Webhook N8N (Iniciar Scraping)' não está configurada. Vá em Configurações -> Pesquisa AIIA para defini-la."))

        # Preparar o payload para enviar ao N8N
        payload = {
            'query': self.search_query,
            'odoo_user_id': self.env.user.id, # Envia ID do usuário que solicitou
            'odoo_user_name': self.env.user.name # Envia nome do usuário
            # Você pode adicionar mais informações se o N8N precisar
        }

        headers = {'Content-Type': 'application/json'}

        _logger.info(f"Iniciando scraping AIIA. Enviando query '{self.search_query}' para {n8n_trigger_url}")

        try:
            # Enviar a requisição para o N8N
            response = requests.post(n8n_trigger_url, headers=headers, json=payload, timeout=10) # Timeout curto, pois N8N deve responder rápido (só confirma recebimento)
            response.raise_for_status() # Levanta erro para status >= 400

            _logger.info(f"Solicitação de scraping enviada com sucesso para N8N. Resposta N8N (status {response.status_code}): {response.text[:200]}") # Loga início da resposta

            # Mostrar notificação de sucesso para o usuário
            notification = {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Pesquisa Iniciada'),
                    'message': _("Sua pesquisa por '%s' foi enviada para processamento. Os resultados aparecerão na lista de Leads Recebidos em breve.", self.search_query),
                    'sticky': False, # Fecha automaticamente
                    'type': 'success',
                }
            }
            return notification

        except requests.exceptions.Timeout:
            _logger.error(f"Timeout ao enviar solicitação de scraping para N8N: {n8n_trigger_url}")
            raise UserError(_("O serviço N8N demorou muito para confirmar o recebimento (Timeout). Verifique se o N8N está ativo e a URL está correta."))
        except requests.exceptions.RequestException as e:
            _logger.error(f"Erro ao enviar solicitação de scraping para N8N: {e}")
            error_details = str(e)
            if e.response is not None:
                try:
                    error_details = e.response.json()
                except json.JSONDecodeError:
                     error_details = e.response.text[:500] # Mostra parte do erro
            raise UserError(_("Erro ao comunicar com o N8N para iniciar a pesquisa: %s", error_details))
        except Exception as e:
             _logger.exception("Erro inesperado ao iniciar scraping:")
             raise UserError(_("Ocorreu um erro inesperado: %s", str(e)))