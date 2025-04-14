# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class PesquisaAiiaSearch(models.Model):
    _name = 'pesquisa_aiia.search'
    _description = 'Registro de Pesquisa AIIA'
    _order = 'create_date desc'

    name = fields.Char(string='Termo Pesquisado', related='search_query', store=True)
    search_query = fields.Text(string='Consulta Original', readonly=True)
    user_id = fields.Many2one('res.users', string='Iniciado por', default=lambda self: self.env.user, readonly=True)
    create_date = fields.Datetime(string='Data da Criação', readonly=True, default=fields.Datetime.now)
    next_page_token = fields.Text(string='Token Próxima Página', readonly=True, copy=False)
    status = fields.Selection([
        ('new', 'Nova'),
        ('processing', 'Processando'),
        ('pending_next', 'Aguardando Próxima Página'),
        ('completed', 'Concluída'),
        ('error', 'Erro')
    ], string='Status', default='new', readonly=True, copy=False)
    lead_ids = fields.One2many('pesquisa_aiia.lead', 'search_id', string='Leads Encontrados')
    lead_count = fields.Integer(string='Nº Leads', compute='_compute_lead_count')
    error_message = fields.Text(string='Mensagem de Erro', readonly=True)

    @api.depends('lead_ids')
    def _compute_lead_count(self):
        for search in self:
            search.lead_count = len(search.lead_ids)

    def _get_n8n_trigger_url(self):
        """Helper para buscar a URL do webhook de trigger."""
        config_params = self.env['ir.config_parameter'].sudo()
        n8n_trigger_url = config_params.get_param('pesquisa_aiia.n8n_scrape_trigger_url')
        if not n8n_trigger_url:
            raise UserError(_("A 'URL Webhook N8N (Iniciar Scraping)' não está configurada. Vá em Configurações -> Pesquisa AIIA."))
        return n8n_trigger_url

    def action_search_next_page(self):
        """Envia o token da próxima página para o N8N."""
        self.ensure_one()
        if not self.next_page_token:
            raise UserError(_("Não há token para a próxima página nesta pesquisa."))
        if self.status == 'processing':
             raise UserError(_("A pesquisa ainda está em processamento. Aguarde."))

        n8n_trigger_url = self._get_n8n_trigger_url()

        payload = {
            'search_id': self.id, # Identifica a pesquisa
            'next_page_token': self.next_page_token, # Envia o token
            'odoo_user_id': self.env.user.id,
            'odoo_user_name': self.env.user.name
            # NÃO envia 'query' aqui, N8N usará o token
        }
        headers = {'Content-Type': 'application/json'}

        _logger.info(f"Solicitando próxima página para pesquisa {self.id} com token. Enviando para {n8n_trigger_url}")
        self.write({'status': 'processing', 'error_message': False}) # Atualiza status

        try:
            response = requests.post(n8n_trigger_url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            _logger.info(f"Solicitação de próxima página para pesquisa {self.id} enviada com sucesso.")
            # A notificação pode ser útil aqui também
            self.env.user.notify_info(message=_("Solicitação para próxima página enviada. Novos leads aparecerão em breve."))

        except Exception as e:
            _logger.error(f"Erro ao enviar solicitação de próxima página para pesquisa {self.id}: {e}")
            error_details = str(e)
            if hasattr(e, 'response') and e.response is not None:
                 try: error_details = e.response.json()
                 except json.JSONDecodeError: error_details = e.response.text[:500]
            # Reverte status e grava erro
            self.write({'status': 'error', 'error_message': f"Erro ao contatar N8N: {error_details}"})
            # Não levanta UserError aqui, apenas registra o erro no modelo
            self.env.user.notify_danger(message=_("Erro ao solicitar próxima página: %s", error_details))

        # Retorna nada ou uma ação de refresh se desejado
        return True

    def action_view_results(self):
        """Abre a lista de leads filtrada por esta pesquisa."""
        self.ensure_one()
        # Pega a ação da lista de leads existente
        action = self.env['ir.actions.act_window']._for_xml_id('pesquisa_aiia.action_pesquisa_aiia_leads')
        # Define o domínio para filtrar pelo ID da pesquisa atual
        action['domain'] = [('search_id', '=', self.id)]
        # Define um contexto para que a view saiba qual pesquisa está sendo vista (útil para defaults)
        action['context'] = dict(self.env.context, default_search_id=self.id, search_default_search_id=self.id)
        # Altera o nome da janela para refletir a pesquisa atual
        action['name'] = _('Leads de "%s"') % (self.name or _('Pesquisa Sem Nome'))
        return action