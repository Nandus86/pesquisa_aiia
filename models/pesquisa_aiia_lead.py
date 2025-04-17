# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import urllib.parse
import re # Para validação básica de telefone
import logging # Adicionado para log

_logger = logging.getLogger(__name__) # Adicionado logger

class PesquisaAiiaLead(models.Model):
    _name = 'pesquisa_aiia.lead'
    _description = 'Lead de Pesquisa AIIA'
    _order = 'create_date desc'
    # Herdar mail.thread para melhor rastreabilidade (opcional, mas bom)
    _inherit = ['mail.thread', 'mail.activity.mixin']

    search_id = fields.Many2one('pesquisa_aiia.search', string='Pesquisa Origem', ondelete='set null', index=True, tracking=True)
    name = fields.Char(string='Nome da Empresa', required=True, tracking=True)
    phone = fields.Char(string='Telefone', tracking=True)
    email = fields.Char(string='E-mail', tracking=True)
    address = fields.Text(string='Endereço', tracking=True)
    activity_summary = fields.Text(string='Resumo da Atividade', tracking=True)
    message_text = fields.Text(string='Texto da Mensagem', default="")
    use_default_message = fields.Boolean(string='Usar Mensagem Padrão?', default=True)

    # --- Campos de Controle ---
    contact_created = fields.Boolean(string='Contato Criado?', default=False, readonly=True, copy=False, tracking=True)
    created_partner_id = fields.Many2one('res.partner', string='Contato Criado Ref.', readonly=True, copy=False, tracking=True,
                                         help="Referência ao registro de Contato (res.partner) criado a partir deste lead.")
    opportunity_created = fields.Boolean(string='Oportunidade Criada?', default=False, readonly=True, copy=False, tracking=True)
    # Poderíamos adicionar um Many2one para crm.lead se quiséssemos linkar diretamente

    # --- Actions Methods ---

    def _get_message_to_send(self):
        """Helper para obter a mensagem correta (padrão ou customizada)."""
        self.ensure_one()
        if self.use_default_message:
            default_msg = self.env['ir.config_parameter'].sudo().get_param('pesquisa_aiia.default_whatsapp_msg', '')
            # Simples substituição de placeholder (pode ser melhorado)
            return (default_msg or '').replace('[Nome da Empresa]', self.name or '')
        else:
            return self.message_text or ''

    def _clean_phone(self, phone_number):
        """Remove caracteres não numéricos. Simples, pode precisar de melhorias."""
        if not phone_number:
            return ''
        # Remove +, -, (, ), ' '
        return re.sub(r'[+\-\(\) ]', '', phone_number)

    def action_send_whatsapp(self):
        self.ensure_one()
        if not self.phone:
            raise UserError(_("Este lead não possui um número de telefone."))

        cleaned_phone = self._clean_phone(self.phone)
        if len(cleaned_phone) <= 11 and not cleaned_phone.startswith('55'):
             cleaned_phone = f"55{cleaned_phone}"

        message = self._get_message_to_send()
        encoded_message = urllib.parse.quote(message)
        whatsapp_url = f"https://wa.me/{cleaned_phone}?text={encoded_message}"

        return {
            'type': 'ir.actions.act_url',
            'url': whatsapp_url,
            'target': 'new',
        }

    def action_send_email(self):
        self.ensure_one()
        if not self.email:
            raise UserError(_("Este lead não possui um endereço de e-mail."))

        config_params = self.env['ir.config_parameter'].sudo()
        default_subject = config_params.get_param('pesquisa_aiia.default_email_subject', _('Contato via Pesquisa AIIA'))
        default_body = config_params.get_param('pesquisa_aiia.default_email_body', '')

        subject_to_send = (default_subject or '').replace('[Nome da Empresa]', self.name or '')
        body_to_send = ''
        if self.use_default_message:
            body_to_send = (default_body or '').replace('[Nome da Empresa]', self.name or '')
        else:
            body_to_send = self.message_text or ''

        compose_form_view_id = self.env.ref('mail.view_mail_compose_message_wizard_form').id

        # Tenta encontrar o parceiro criado ou buscar por email
        partner_to = self.created_partner_id or self.env['res.partner'].search([('email', '=', self.email)], limit=1)

        ctx = {
            'default_model': 'pesquisa_aiia.lead',
            'default_res_id': self.id,
            'default_use_template': False,
            'default_partner_ids': partner_to.ids,
            'default_email_to': self.email if not partner_to else partner_to.email, # Usa email do lead se não achou parceiro
            'default_subject': subject_to_send,
            'default_body': body_to_send,
            'custom_layout': "mail.mail_notification_light",
            'force_email': True,
            'mark_so_sent': True, # Marca a mensagem como enviada
        }

        return {
            'type': 'ir.actions.act_window',
            'name': _('Enviar E-mail'),
            'res_model': 'mail.compose.message',
            'views': [(compose_form_view_id, 'form')],
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def action_delete_lead(self):
        # Poderia adicionar log antes de deletar
        _logger.info(f"Usuário {self.env.user.name} deletando lead AIIA ID: {self.ids}")
        return self.unlink()

    def action_create_contact(self):
        self.ensure_one()
        Partner = self.env['res.partner']

        if self.contact_created:
             # Poderia retornar uma ação para visualizar o contato existente
             if self.created_partner_id:
                 return {
                    'type': 'ir.actions.act_window',
                    'name': _('Contato Existente'),
                    'res_model': 'res.partner',
                    'res_id': self.created_partner_id.id,
                    'view_mode': 'form',
                    'target': 'current',
                 }
             else:
                 raise UserError(_("Um contato já foi marcado como criado para este lead, mas a referência foi perdida."))

        # Verificar se já existe um contato com este email OU telefone (manter ou remover?)
        # Remover a verificação por telefone pode ser menos restritivo
        # existing_partner = Partner.search(['|', ('email', '=', self.email), ('phone', '=', self.phone)], limit=1)
        existing_partner = Partner.search([('email', '=ilike', self.email)], limit=1) # Busca por email (case-insensitive)
        if existing_partner:
            # O que fazer? Ligar a este? Criar novo? Dar erro? Vamos dar erro por enquanto.
            # Para ligar: self.write({'contact_created': True, 'created_partner_id': existing_partner.id}) e retornar ação de visualização.
            raise UserError(_("Já existe um contato com este e-mail: %s (ID: %d)", existing_partner.name, existing_partner.id))

        try:
            new_partner_vals = {
                'name': self.name,
                'phone': self.phone,
                'email': self.email,
                'street': self.address,
                'comment': self.activity_summary + f"\n\nOrigem: Pesquisa AIIA (Lead ID: {self.id}, Pesquisa ID: {self.search_id.id if self.search_id else 'N/A'})",
                'is_company': True,
            }
            new_partner = Partner.create(new_partner_vals)
            # *** MODIFICAÇÃO: Salvar a referência e logar ***
            self.write({'contact_created': True, 'created_partner_id': new_partner.id})
            self.message_post(body=_("Contato %s criado a partir deste lead por %s.") % (new_partner.name, self.env.user.name))
            _logger.info(f"Contato {new_partner.id} ({new_partner.name}) criado a partir do Lead AIIA {self.id}")

            # Retorna ação para ver o contato criado
            return {
                'type': 'ir.actions.act_window',
                'name': _('Contato Criado'),
                'res_model': 'res.partner',
                'res_id': new_partner.id,
                'view_mode': 'form',
                'target': 'current',
            }

        except Exception as e:
             _logger.exception(f"Erro ao criar contato para Lead AIIA {self.id}: {e}")
             raise UserError(_("Erro ao criar contato: %s", str(e)))

    # --- NOVO MÉTODO ---
    def action_create_opportunity(self):
        self.ensure_one()

        # 1. Verificar se o módulo CRM está instalado
        crm_module = self.env['ir.module.module'].sudo().search([('name', '=', 'crm'), ('state', '=', 'installed')])
        if not crm_module:
            raise UserError(_("O módulo CRM não está instalado. Instale-o para criar oportunidades."))

        # 2. Verificar se a oportunidade já foi criada
        if self.opportunity_created:
            # Opcional: Buscar e mostrar a oportunidade existente se tivéssemos um campo Many2one
            raise UserError(_("Uma oportunidade já foi criada para este lead."))

        # 3. Obter o modelo crm.lead
        Opportunity = self.env['crm.lead']

        # 4. Preparar valores para a nova oportunidade
        opportunity_name = f"Oportunidade: {self.name}" # Nome da oportunidade
        description = f"Resumo da Atividade:\n{self.activity_summary or 'N/A'}\n\n" \
                      f"Origem: Pesquisa AIIA\n" \
                      f"- Lead AIIA ID: {self.id}\n" \
                      f"- Pesquisa ID: {self.search_id.id if self.search_id else 'N/A'}\n" \
                      f"- Termo Pesquisado: {self.search_id.name if self.search_id else 'N/A'}"

        opportunity_vals = {
            'name': opportunity_name,
            'partner_id': self.created_partner_id.id if self.created_partner_id else None, # Linka o contato se criado
            'email_from': self.email,
            'phone': self.phone,
            'description': description,
            'type': 'opportunity', # Criar diretamente como oportunidade (ou 'lead' se preferir)
            'user_id': self.env.user.id, # Atribui ao usuário atual
            # 'team_id': ID_DA_EQUIPE_PADRAO, # Opcional: Definir equipe de vendas
            # 'contact_name': self.name, # Opcional: Nome do contato se não houver parceiro
            # 'street': self.address, # Opcional
        }

        # Se não linkou parceiro existente, tenta encontrar por email (opcional)
        if not opportunity_vals['partner_id'] and self.email:
            partner = self.env['res.partner'].search([('email', '=ilike', self.email)], limit=1)
            if partner:
                opportunity_vals['partner_id'] = partner.id

        # 5. Criar a oportunidade
        try:
            new_opportunity = Opportunity.create(opportunity_vals)
            # 6. Marcar o lead como processado e logar
            self.write({'opportunity_created': True})
            self.message_post(body=_("Oportunidade '%s' (ID: %d) criada no CRM por %s.") % (new_opportunity.name, new_opportunity.id, self.env.user.name))
            _logger.info(f"Oportunidade {new_opportunity.id} ({new_opportunity.name}) criada a partir do Lead AIIA {self.id}")

            # 7. Retornar ação para visualizar a oportunidade
            return {
                'type': 'ir.actions.act_window',
                'name': _('Oportunidade Criada'),
                'res_model': 'crm.lead',
                'res_id': new_opportunity.id,
                'view_mode': 'form',
                'target': 'current', # Abrir na mesma aba
            }

        except Exception as e:
            _logger.exception(f"Erro ao criar oportunidade CRM para Lead AIIA {self.id}: {e}")
            raise UserError(_("Erro ao criar oportunidade: %s", str(e)))