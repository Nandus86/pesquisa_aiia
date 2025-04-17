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
    # --- TOKEN FIELD ---
    next_page_token = fields.Text(string='Token Próxima Página', readonly=True, copy=False,
                                 help="Token fornecido pela API externa para buscar a próxima página de resultados.")
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
    # Opcional: Armazenar a mensagem inicial
    # initial_message = fields.Text(string='Mensagem Inicial Usada', readonly=True)

    @api.depends('search_query')
    def _compute_name(self):
        for search in self:
            # ... (código igual)
            if search.search_query:
                query = search.search_query
                search.name = query[:100] + ('...' if len(query) > 100 else '')
            else:
                search.name = _('Pesquisa Vazia')

    @api.depends('lead_ids')
    def _compute_lead_count(self):
        for search in self:
            # Usar search_count é mais performático para muitos leads
            search.lead_count = self.env['pesquisa_aiia.lead'].search_count([('search_id', '=', search.id)])

    def _get_n8n_trigger_url(self):
        # ... (código igual)
        config_params = self.env['ir.config_parameter'].sudo()
        n8n_trigger_url = config_params.get_param('pesquisa_aiia.n8n_scrape_trigger_url')
        if not n8n_trigger_url:
            raise UserError(_("A 'URL Webhook N8N (Iniciar Scraping)' não está configurada."))
        return n8n_trigger_url

    def _send_request_to_n8n(self, payload):
        # ... (código interno de envio, tratamento de erro e status igual ao anterior) ...
        # Importante: este método apenas ENVIA o payload recebido.
        # A lógica de *qual* payload enviar (com query ou com token)
        # está nos métodos que chamam este (_start_new_search_request, _search_next_page_request).
        self.ensure_one()
        n8n_trigger_url = self._get_n8n_trigger_url()
        headers = {'Content-Type': 'application/json'}

        _logger.info(f"Enviando payload para N8N (Search ID: {self.id}): {json.dumps(payload)}")

        # Garante que status vá para 'processing' e limpa erros
        write_vals = {'status': 'processing', 'error_message': False}
        # NUNCA limpar token aqui, ele só é atualizado pelo webhook /update_search
        self.write(write_vals)
        self.env.cr.commit() # Garante atualização antes da chamada externa

        try:
            response = requests.post(n8n_trigger_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            _logger.info(f"Solicitação (Search ID: {self.id}) enviada com sucesso para N8N. Resposta N8N (status {response.status_code}): {response.text[:200]}")
            # Aguarda o webhook /update_search para mudar o status de 'processing'
            return True

        except requests.exceptions.Timeout:
            _logger.error(f"Timeout ao enviar solicitação (Search ID: {self.id}): {n8n_trigger_url}")
            error_msg = _("Timeout N8N: O serviço externo demorou muito para responder.")
            self.write({'status': 'error', 'error_message': error_msg})
            self.env.cr.commit()
            raise UserError(error_msg)
        except requests.exceptions.RequestException as e:
            _logger.error(f"Erro ao enviar solicitação (Search ID: {self.id}): {e}")
            error_details = str(e)
            if hasattr(e, 'response') and e.response is not None:
                 try: error_details = e.response.json()
                 except json.JSONDecodeError: error_details = e.response.text[:500]
            error_msg_user = _("Erro N8N: %s", error_details)
            self.write({'status': 'error', 'error_message': error_msg_user})
            self.env.cr.commit()
            raise UserError(error_msg_user)
        except Exception as e:
             _logger.exception(f"Erro inesperado ao enviar para N8N (Search ID: {self.id}):")
             error_msg = _("Erro inesperado: %s", str(e))
             self.write({'status': 'error', 'error_message': error_msg})
             self.env.cr.commit()
             raise UserError(error_msg)


    # --- MÉTODO PARA INICIAR NOVA PESQUISA (Chamado pelo Wizard) ---
    @api.model
    def start_new_search(self, query, message=None):
        """
        Cria um novo registro de pesquisa e envia a solicitação INICIAL para N8N.
        Não usa next_page_token.
        """
        if not query or not query.strip():
            raise ValidationError(_("O termo de pesquisa não pode estar vazio."))

        search_record = self.create({
            'search_query': query.strip(),
            'user_id': self.env.user.id,
            'status': 'new',
            # 'initial_message': message, # Descomente se criou o campo
        })
        _logger.info(f"Novo registro de pesquisa criado ID: {search_record.id} para query: '{query}'")

        # Payload para INICIAR a pesquisa
        payload = {
            'search_id': search_record.id,
            'query': search_record.search_query, # Envia a query original
            'message': message,                  # Envia a mensagem inicial
            'odoo_user_id': search_record.user_id.id,
            'odoo_user_name': search_record.user_id.name
            # NÂO envia next_page_token aqui
        }

        try:
            # Chama o método de envio interno
            search_record._send_request_to_n8n(payload)
            return search_record.id # Retorna ID para o wizard
        except (UserError, ValidationError) as e:
            # Se o envio falhar, o status já foi para 'error'. Repassa o erro.
            # Considerar deletar o registro se o envio inicial falhar?
            # search_record.unlink()
            raise e


    # --- MÉTODO PARA BUSCAR PRÓXIMA PÁGINA (Chamado pela Server Action/Botão Form) ---
    def search_next_page(self):
        """
        Envia a solicitação da PRÓXIMA PÁGINA para N8N usando o token armazenado.
        """
        self.ensure_one()

        # Validações
        if not self.next_page_token:
            raise UserError(_("Não há token para solicitar a próxima página. A pesquisa pode ter sido concluída ou falhado."))
        if self.status in ['processing', 'new']: # Não pode buscar se já está processando ou é nova
             raise UserError(_("Aguarde o processamento anterior ser concluído (status deve ser 'Aguardando Próxima Página')."))
        if self.status == 'error':
            raise UserError(_("Não é possível buscar a próxima página para uma pesquisa com erro."))
        if self.status == 'completed':
             raise UserError(_("Esta pesquisa já foi concluída."))

        _logger.info(f"Solicitando próxima página para Search ID: {self.id} usando token.")

        # Payload para CONTINUAR a pesquisa
        payload = {
            'search_id': self.id,
            'next_page_token': self.next_page_token, # Envia o token armazenado
            'odoo_user_id': self.user_id.id,
            'odoo_user_name': self.user_id.name
            # NÃO envia a query original nem a mensagem inicial aqui
        }

        try:
             # Chama o mesmo método de envio interno
             self._send_request_to_n8n(payload)
             # Se chegou aqui, a requisição foi enviada. Aguarda webhook de update.
             return True # Indica sucesso para a Server Action/Botão
        except (UserError, ValidationError) as e:
             # Repassa o erro que já atualizou o status para 'error'
             raise e

    # --- Ação para ver resultados (igual) ---
    def action_view_results(self):
        # ... (código igual)
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('pesquisa_aiia.action_pesquisa_aiia_leads')
        action['domain'] = [('search_id', '=', self.id)]
        action['context'] = {'default_search_id': self.id}
        return action