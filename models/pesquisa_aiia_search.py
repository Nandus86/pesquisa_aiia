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
    _inherit = ['mail.thread', 'mail.activity.mixin']

    search_query = fields.Text(string='Consulta Original', readonly=True, required=True, tracking=True)
    name = fields.Char(string='Termo Pesquisado (Resumo)', compute='_compute_name', store=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Iniciado por', default=lambda self: self.env.user, readonly=True, tracking=True)
    create_date = fields.Datetime(string='Data da Criação', readonly=True, default=fields.Datetime.now)
    next_page_token = fields.Text(string='Token Próxima Página', readonly=True, copy=False,
                                 help="Token fornecido pela API externa para buscar a próxima página de resultados.")
    status = fields.Selection([
        ('new', 'Nova'),
        ('processing', 'Processando'),
        ('pending_next', 'Aguardando Próxima Página'),
        ('completed', 'Concluída'),
        ('error', 'Erro')
    ], string='Status', default='new', readonly=True, copy=False, index=True, tracking=True)
    lead_ids = fields.One2many('pesquisa_aiia.lead', 'search_id', string='Leads Encontrados')
    # *** CORREÇÃO AQUI: Simplificando o método de cálculo ***
    lead_count = fields.Integer(string='Nº Leads', compute='_compute_lead_count')
    error_message = fields.Text(string='Mensagem de Erro', readonly=True, tracking=True)

    @api.depends('search_query')
    def _compute_name(self):
        for search in self:
            if search.search_query:
                query = search.search_query
                search.name = query[:100] + ('...' if len(query) > 100 else '')
            else:
                search.name = _('Pesquisa Vazia')

    # *** CORREÇÃO AQUI: Usando search_count para simplicidade e evitar erro de agregação ***
    @api.depends('lead_ids')
    def _compute_lead_count(self):
        for search in self:
            search.lead_count = self.env['pesquisa_aiia.lead'].search_count([('search_id', '=', search.id)])

    def _get_n8n_trigger_url(self):
        config_params = self.env['ir.config_parameter'].sudo()
        n8n_trigger_url = config_params.get_param('pesquisa_aiia.n8n_scrape_trigger_url')
        if not n8n_trigger_url:
            raise UserError(_("A 'URL Webhook N8N (Iniciar Scraping)' não está configurada."))
        return n8n_trigger_url

    def _send_request_to_n8n(self, payload):
        self.ensure_one()
        n8n_trigger_url = self._get_n8n_trigger_url()
        headers = {'Content-Type': 'application/json'}

        _logger.info(f"Enviando payload para N8N (Search ID: {self.id}): {json.dumps(payload)}")

        old_status = self.status
        new_status = 'processing'

        write_vals = {'status': new_status, 'error_message': False}
        # Usar _write para evitar recursão infinita se o tracking estiver no status
        # ou garantir que a lógica de log do write não seja acionada duas vezes.
        # Neste caso, como temos um write customizado, vamos chamá-lo para logar.
        self.write(write_vals)
        # O log já é feito pelo método write sobrescrito
        # self.message_post(body=_("Status alterado de '%s' para '%s' ao enviar requisição para N8N.") % (old_status, new_status))
        self.env.cr.commit()

        try:
            response = requests.post(n8n_trigger_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            _logger.info(f"Solicitação (Search ID: {self.id}) enviada com sucesso para N8N. Resposta N8N (status {response.status_code}): {response.text[:200]}")
            return True

        except requests.exceptions.Timeout:
            _logger.error(f"Timeout ao enviar solicitação (Search ID: {self.id}): {n8n_trigger_url}")
            error_msg = _("Timeout N8N: O serviço externo demorou muito para responder.")
            self.write({'status': 'error', 'error_message': error_msg}) # Write chamará message_post
            self.env.cr.commit()
            raise UserError(error_msg)
        except requests.exceptions.RequestException as e:
            _logger.error(f"Erro ao enviar solicitação (Search ID: {self.id}): {e}")
            error_details = str(e)
            if hasattr(e, 'response') and e.response is not None:
                 try: error_details = e.response.json()
                 except json.JSONDecodeError: error_details = e.response.text[:500]
            error_msg_user = _("Erro N8N: %s", error_details)
            self.write({'status': 'error', 'error_message': error_msg_user}) # Write chamará message_post
            self.env.cr.commit()
            raise UserError(error_msg_user)
        except Exception as e:
             _logger.exception(f"Erro inesperado ao enviar para N8N (Search ID: {self.id}):")
             error_msg = _("Erro inesperado: %s", str(e))
             self.write({'status': 'error', 'error_message': error_msg}) # Write chamará message_post
             self.env.cr.commit()
             raise UserError(error_msg)

    @api.model_create_multi
    def create(self, vals_list):
        records = super(PesquisaAiiaSearch, self).create(vals_list)
        for record in records:
            record.message_post(body=_("Pesquisa criada por %s com o termo: '%s'") % (record.user_id.name, record.search_query))
        return records

    @api.model
    def start_new_search(self, query, message=None):
        if not query or not query.strip():
            raise ValidationError(_("O termo de pesquisa não pode estar vazio."))

        search_record = self.create({
            'search_query': query.strip(),
            'user_id': self.env.user.id,
            'status': 'new',
        })
        _logger.info(f"Novo registro de pesquisa criado ID: {search_record.id} para query: '{query}'")

        payload = {
            'search_id': search_record.id,
            'query': search_record.search_query,
            'message': message,
            'odoo_user_id': search_record.user_id.id,
            'odoo_user_name': search_record.user_id.name
        }

        try:
            search_record._send_request_to_n8n(payload)
            return search_record.id
        except (UserError, ValidationError) as e:
            raise e

    def search_next_page(self):
        self.ensure_one()

        if not self.next_page_token:
            raise UserError(_("Não há token para solicitar a próxima página."))
        if self.status in ['processing', 'new']:
             raise UserError(_("Aguarde o processamento anterior ser concluído."))
        if self.status == 'error':
            raise UserError(_("Não é possível buscar a próxima página para uma pesquisa com erro."))
        if self.status == 'completed':
             raise UserError(_("Esta pesquisa já foi concluída."))

        _logger.info(f"Solicitando próxima página para Search ID: {self.id} usando token.")
        self.message_post(body=_("Solicitando próxima página de resultados."))

        payload = {
            'search_id': self.id,
            'next_page_token': self.next_page_token,
            'odoo_user_id': self.user_id.id,
            'odoo_user_name': self.user_id.name
        }

        try:
             self._send_request_to_n8n(payload)
             return True
        except (UserError, ValidationError) as e:
             raise e

    def action_view_results(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('pesquisa_aiia.action_pesquisa_aiia_leads')
        action['name'] = _('Leads da Pesquisa: %s') % self.name
        action['display_name'] = action['name']
        action['domain'] = [('search_id', '=', self.id)]
        action['context'] = {'default_search_id': self.id, 'search_default_search_id': self.id}
        return action

    def write(self, vals):
        old_status_map = {}
        if 'status' in vals:
            # Somente buscar o status antigo se ele estiver sendo alterado
            old_status_map = {rec.id: rec.status for rec in self}

        res = super(PesquisaAiiaSearch, self).write(vals)

        # Logar mudança de status APÓS a escrita ser bem sucedida
        if 'status' in vals:
            new_status = vals['status']
            for record in self.filtered(lambda r: r.id in old_status_map): # Apenas nos registros que tiveram status avaliado
                old_status = old_status_map.get(record.id)
                # Loga apenas se o status realmente mudou
                if old_status != new_status:
                    message = _("Status alterado de '%s' para '%s'") % (self.env['pesquisa_aiia.search']._fields['status']._description_selection(self.env)[old_status],
                                                                          self.env['pesquisa_aiia.search']._fields['status']._description_selection(self.env)[new_status])
                    error_msg_val = vals.get('error_message', record.error_message) # Pega da escrita ou do registro
                    next_page_token_val = vals.get('next_page_token', record.next_page_token)

                    if new_status == 'error' and error_msg_val:
                         message += _(" - Erro: %s") % error_msg_val
                    elif new_status == 'pending_next' and next_page_token_val:
                         message += _(". Próxima página disponível.")
                    elif new_status == 'completed':
                         message += _(". Pesquisa concluída.")

                    record.message_post(body=message, message_type='comment', subtype_xmlid='mail.mt_comment')
        return res