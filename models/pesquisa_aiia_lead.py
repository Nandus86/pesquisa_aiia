# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import urllib.parse
import re # Para validação básica de telefone

class PesquisaAiiaLead(models.Model):
    _name = 'pesquisa_aiia.lead'
    _description = 'Lead de Pesquisa AIIA'
    _order = 'create_date desc' # Ordena os mais recentes primeiro

    name = fields.Char(string='Nome da Empresa', required=True)
    phone = fields.Char(string='Telefone')
    email = fields.Char(string='E-mail')
    address = fields.Text(string='Endereço')
    activity_summary = fields.Text(string='Resumo da Atividade')
    message_text = fields.Text(string='Texto da Mensagem', default="")
    use_default_message = fields.Boolean(string='Usar Mensagem Padrão?', default=True)
    contact_created = fields.Boolean(string='Contato Criado?', default=False, readonly=True, copy=False)

    # --- Actions Methods ---

    def _get_message_to_send(self):
        """Helper para obter a mensagem correta (padrão ou customizada)."""
        self.ensure_one()
        if self.use_default_message:
            default_msg = self.env['ir.config_parameter'].sudo().get_param('pesquisa_aiia.default_whatsapp_msg', '')
            return default_msg
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
        # Adiciona o código do país se não estiver presente (exemplo: Brasil '55')
        # Adapte conforme necessário para sua região
        if len(cleaned_phone) <= 11 and not cleaned_phone.startswith('55'): # Simples verificação de tamanho
             cleaned_phone = f"55{cleaned_phone}"

        message = self._get_message_to_send()
        encoded_message = urllib.parse.quote(message)

        # Gera a URL do WhatsApp Click-to-Chat
        whatsapp_url = f"https://wa.me/{cleaned_phone}?text={encoded_message}"

        # Retorna uma ação para abrir a URL em uma nova aba
        return {
            'type': 'ir.actions.act_url',
            'url': whatsapp_url,
            'target': 'new', # Abre em nova aba
        }

    def action_send_email(self):
        self.ensure_one()
        if not self.email:
            raise UserError(_("Este lead não possui um endereço de e-mail."))

        # Buscar configurações padrão
        config_params = self.env['ir.config_parameter'].sudo()
        default_subject = config_params.get_param('pesquisa_aiia.default_email_subject', _('Contato via Pesquisa AIIA'))
        default_body = config_params.get_param('pesquisa_aiia.default_email_body', '')

        # Determinar assunto e corpo
        subject_to_send = default_subject # Assunto não costuma variar tanto, mas pode ser adaptado
        if self.use_default_message:
            body_to_send = default_body
        else:
            body_to_send = self.message_text or ''

        # Usar um template de email ou criar um mail.mail simples pode ser mais robusto
        # Aqui, abriremos o compositor de e-mail pré-preenchido

        compose_form_view_id = self.env.ref('mail.view_mail_compose_message_wizard_form').id

        ctx = {
            'default_model': 'pesquisa_aiia.lead',
            'default_res_id': self.id,
            'default_use_template': False, # Não estamos usando um mail.template aqui
            'default_partner_ids': [], # Não temos um parceiro ainda, mas podemos tentar encontrar
            'default_email_to': self.email,
            'default_subject': subject_to_send,
            'default_body': body_to_send, # Odoo usa HTML, texto simples pode precisar de formatação
            'custom_layout': "mail.mail_notification_light", # Layout simples
            'force_email': True, # Garante que seja tratado como email
        }

        # Tentar encontrar parceiro existente pelo email para preencher melhor o TO
        partner = self.env['res.partner'].search([('email', '=', self.email)], limit=1)
        if partner:
             ctx['default_partner_ids'] = partner.ids


        return {
            'type': 'ir.actions.act_window',
            'name': _('Enviar E-mail'),
            'res_model': 'mail.compose.message',
            'views': [(compose_form_view_id, 'form')],
            'view_mode': 'form',
            'target': 'new', # Abre em pop-up
            'context': ctx,
        }

    def action_delete_lead(self):
        # A exclusão padrão já funciona pelo botão delete, mas podemos adicionar lógica se necessário
        # Por exemplo, pedir confirmação extra ou logar a ação.
        # Aqui, apenas chamamos o unlink padrão.
        return self.unlink() # unlink já tem controle de acesso

    def action_create_contact(self):
        self.ensure_one()
        Partner = self.env['res.partner']

        if self.contact_created:
             raise UserError(_("Um contato já foi criado para este lead."))

        # Verificar se já existe um contato com este email ou telefone? (Opcional)
        existing_partner = Partner.search(['|', ('email', '=', self.email), ('phone', '=', self.phone)], limit=1)
        if existing_partner:
            raise UserError(_("Já existe um contato com este e-mail ou telefone: %s", existing_partner.name))

        # Criar o novo contato
        try:
            new_partner_vals = {
                'name': self.name,
                'phone': self.phone,
                'email': self.email,
                'street': self.address, # Mapeamento simples, pode precisar refinar
                'comment': self.activity_summary, # Usar campo de Notas internas
                'is_company': True, # Assumindo que é uma empresa
                # Adicione outros mapeamentos se necessário (website, etc.)
            }
            new_partner = Partner.create(new_partner_vals)
            self.write({'contact_created': True}) # Marca o lead como processado

            # Opcional: Exibir o contato recém-criado
            return {
                'type': 'ir.actions.act_window',
                'name': _('Contato Criado'),
                'res_model': 'res.partner',
                'res_id': new_partner.id,
                'view_mode': 'form',
                'target': 'current', # Abre na mesma janela
            }

        except Exception as e:
             raise UserError(_("Erro ao criar contato: %s", str(e)))