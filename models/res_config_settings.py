# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # --- Configurações Pesquisa AIIA ---
    # Usamos config_parameter para armazenar globalmente
    aiia_webhook_url = fields.Char(
        string='URL Webhook N8N (Leitura)',
        readonly=True, # Apenas exibe, a URL real está no controller
        help="A URL para configurar no N8N é: [Sua URL Odoo]/pesquisa_aiia/webhook"
    )
    aiia_webhook_secret = fields.Char(
        string='Segredo Webhook (Opcional)',
        config_parameter='pesquisa_aiia.webhook_secret',
        help="Um segredo opcional para validar a origem do webhook."
    )
    aiia_default_whatsapp_msg = fields.Char(
        string='Mensagem Padrão WhatsApp',
        config_parameter='pesquisa_aiia.default_whatsapp_msg',
        default="Olá [Nome da Empresa], vimos sua atividade e gostaríamos de conversar." # Exemplo
    )
    aiia_default_email_subject = fields.Char(
        string='Assunto Padrão E-mail',
        config_parameter='pesquisa_aiia.default_email_subject',
        default="Contato referente à sua empresa" # Exemplo
    )
    aiia_default_email_body = fields.Char(
        string='Corpo Padrão E-mail',
        config_parameter='pesquisa_aiia.default_email_body',
        default="""\
Prezados da [Nome da Empresa],

Escrevemos referente à atividade de sua empresa.

Atenciosamente,
Sua Equipe
""" # Exemplo
    )
    aiia_n8n_scrape_trigger_url = fields.Char(
        string='URL Webhook N8N (Iniciar Scraping)',
        config_parameter='pesquisa_aiia.n8n_scrape_trigger_url',
        help="URL do webhook no N8N que recebe a solicitação de pesquisa do Odoo."
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        # Monta a URL de exemplo para exibição
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', default='http://localhost:8069')
        res.update(
            aiia_webhook_url=f"{base_url}/pesquisa_aiia/webhook"
        )
        return res