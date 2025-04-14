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

    search_query = fields.Text(string='Consulta Original', readonly=True, required=True)
    name = fields.Char(string='Termo Pesquisado (Resumo)', compute='_compute_name', store=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Iniciado por', default=lambda self: self.env.user, readonly=True)
    create_date = fields.Datetime(string='Data da Criação', readonly=True, default=fields.Datetime.now)
    next_page_token = fields.Text(string='Token Próxima Página', readonly=True, copy=False)
    status = fields.Selection([
        ('new', 'Nova'),
        ('processing', 'Processando'),
        ('pending_next', 'Aguardando Próxima Página'),
        ('completed', 'Concluída'),
        ('error', 'Erro')
    ], string='Status', default='new', readonly=True, copy=False, index=True)
    lead_ids = fields.One2many('pesquisa_aiia.lead', 'search_id', string='Leads Encontrados')
    lead_count = fields.Integer(string='Nº Leads', compute='_compute_lead_count')
    error_message = fields.Text(string='Mensagem de Erro', readonly=True)

    @api.depends('search_query')
    def _compute_name(self):
        for search in self:
            if search.search_query:
                query = search.search_query
                search.name = query[:100] + ('...' if len(query) > 100 else '')
            else:
                search.name = _('Pesquisa Vazia')

    @api.depends('lead_ids')
    def _compute_lead_count(self):
        for search in self:
            search.lead_count = len(search.lead_ids)

    def _get_n8n_trigger_url(self):
        config_params = self.env['ir.config_parameter'].sudo()
        n8n_trigger_url = config_params.get_param('pesquisa_aiia.n8n_scrape_trigger_url')
        if not n8n_trigger_url:
            raise UserError(_("A 'URL Webhook N8N (Iniciar Scraping)' não está configurada."))
        return n8n_trigger_url

    def _send_request_to_n8n(self, payload):
        """ Envia a requisição (nova ou próxima página) para N8N """
        self.ensure_one() # Garante que estamos operando em um único registro de pesquisa
        n8n_trigger_url = self._get_n8n_trigger_url()
        headers = {'Content-Type': 'application/json'}

        # Log detalhado do payload sendo enviado
        _logger.info(f"Enviando payload para N8N (Search ID: {self.id}): {json.dumps(payload)}")
        self.write({'status': 'processing', 'error_message': False}) # Sempre marca como processando

        try:
            response = requests.post(n8n_trigger_url, headers=headers, json=payload, timeout=15) # Aumenta um pouco o timeout
            response.raise_for_status()
            _logger.info(f"Solicitação (Search ID: {self.id}) enviada com sucesso para N8N. Resposta N8N (status {response.status_code}): {response.text[:200]}")
            return True # Indica sucesso no envio

        except requests.exceptions.Timeout:
            _logger.error(f"Timeout ao enviar solicitação (Search ID: {self.id}): {n8n_trigger_url}")
            self.write({'status': 'error', 'error_message': f"Timeout N8N: {n8n_trigger_url}"})
            # Levanta UserError para notificar o usuário via componente OWL
            raise UserError(_("O serviço N8N demorou muito para responder (Timeout)."))
        except requests.exceptions.RequestException as e:
            _logger.error(f"Erro ao enviar solicitação (Search ID: {self.id}): {e}")
            error_details = str(e)
            if hasattr(e, 'response') and e.response is not None:
                 try: error_details = e.response.json()
                 except json.JSONDecodeError: error_details = e.response.text[:500]
            self.write({'status': 'error', 'error_message': f"Erro N8N: {error_details}"})
            raise UserError(_("Erro ao comunicar com o N8N: %s", error_details))
        except Exception as e:
             _logger.exception(f"Erro inesperado (Search ID: {self.id}):")
             self.write({'status': 'error', 'error_message': f"Erro inesperado: {str(e)}"})
             raise UserError(_("Ocorreu um erro inesperado: %s", str(e)))

    # --- NOVO MÉTODO DE CLASSE PARA SER CHAMADO VIA RPC ---
    @api.model
    def start_new_search(self, query):
        """Cria um novo registro de pesquisa e envia a solicitação inicial para N8N."""
        if not query or not query.strip():
            raise ValidationError(_("O termo de pesquisa não pode estar vazio."))

        search_record = self.create({
            'search_query': query.strip(),
            'user_id': self.env.user.id,
            'status': 'new',
        })
        _logger.info(f"Novo registro de pesquisa criado com ID: {search_record.id} para query: '{query}'")

        payload = {
            'search_id': search_record.id,
            'query': search_record.search_query,
            'odoo_user_id': search_record.user_id.id,
            'odoo_user_name': search_record.user_id.name
        }

        # Chama o método de instância para enviar, tratando erros
        try:
            search_record._send_request_to_n8n(payload)
            # Retorna o ID se o envio foi bem sucedido (sem exceção)
            return search_record.id
        except UserError as ue:
            # Se _send_request_to_n8n levantar UserError, repassa para o cliente OWL
             raise ue
        # Não precisa de except Exception aqui, _send_request já trata e loga

    # --- MÉTODO DE INSTÂNCIA PARA PRÓXIMA PÁGINA (Modificado para ser chamado via RPC) ---
    def search_next_page(self):
        """ Prepara e envia a solicitação da próxima página para N8N. Chamado via RPC."""
        self.ensure_one() # Garante que a chamada RPC seja para um único registro
        if not self.next_page_token:
            raise UserError(_("Não há token para a próxima página nesta pesquisa."))
        if self.status == 'processing':
             raise UserError(_("A pesquisa ainda está em processamento. Aguarde."))

        payload = {
            'search_id': self.id,
            'next_page_token': self.next_page_token,
            'odoo_user_id': self.user_id.id, # Usa o user_id do registro
            'odoo_user_name': self.user_id.name
        }

        # Chama o método de envio
        try:
             self._send_request_to_n8n(payload)
             return True # Indica sucesso para o cliente OWL
        except UserError as ue:
             raise ue # Repassa o erro

    def action_view_results(self):
        # (Método igual)
        pass