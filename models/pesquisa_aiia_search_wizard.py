# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class PesquisaAiiaSearchWizard(models.TransientModel):
    _name = 'pesquisa_aiia.search.wizard'
    _description = 'Assistente para Iniciar Nova Pesquisa AIIA'

    search_query = fields.Char(string='Termo da Pesquisa', required=True)
    # --- CAMPOS PARA MENSAGEM ---
    use_default_message = fields.Boolean(string='Usar Mensagem Padrão?', default=True,
                                         help="Se marcado, usará a mensagem padrão definida nas configurações. Se desmarcado, você deve fornecer uma mensagem personalizada.")
    custom_message = fields.Text(string='Mensagem Personalizada') # Alterado para Text para mensagens mais longas

    # --- Campo auxiliar para controle de visibilidade no XML ---
    @api.depends('use_default_message')
    def _compute_show_custom_message(self):
         for record in self:
              record.show_custom_message = not record.use_default_message

    show_custom_message = fields.Boolean(compute='_compute_show_custom_message', store=False)
    # --- FIM CAMPOS MENSAGEM ---


    def _get_message_to_send(self):
        """ Pega a mensagem correta (padrão das config ou customizada do wizard) """
        self.ensure_one()
        if self.use_default_message:
            # Busca a mensagem padrão configurada nos Ajustes
            # IMPORTANTE: Usar a chave correta definida em res.config.settings
            # Vamos assumir que é 'pesquisa_aiia.default_whatsapp_msg' como estava antes.
            # Considere se precisa de uma mensagem padrão *diferente* para iniciar a pesquisa.
            default_msg = self.env['ir.config_parameter'].sudo().get_param('pesquisa_aiia.default_whatsapp_msg', '')
            _logger.info("Wizard: Usando mensagem padrão das configurações.")
            return default_msg # Retorna a mensagem padrão (pode ser vazia se não configurada)
        else:
            # Verifica se a mensagem customizada foi preenchida
            if not self.custom_message or not self.custom_message.strip():
                 # Levanta um erro se desmarcou "Usar Padrão" mas não digitou nada
                 raise UserError(_("Você escolheu usar uma mensagem personalizada, mas não a digitou."))
            _logger.info("Wizard: Usando mensagem personalizada fornecida.")
            return self.custom_message.strip() # Retorna a mensagem digitada

    def action_start_search(self):
        """ Ação do botão 'Pesquisar' no wizard. """
        self.ensure_one()
        if not self.search_query or not self.search_query.strip():
            # Validação extra no backend
            raise UserError(_("Por favor, informe um termo para pesquisar."))

        # Obtém a mensagem a ser enviada (padrão ou customizada)
        message_to_send = self._get_message_to_send() # Já trata o erro se custom for vazia

        try:
            _logger.info(f"Wizard: Iniciando pesquisa para query '{self.search_query}'...")
            # Chama o método no modelo principal 'pesquisa_aiia.search'
            # **Passando a mensagem obtida**
            search_id = self.env['pesquisa_aiia.search'].start_new_search(
                query=self.search_query.strip(),
                message=message_to_send # Passa a mensagem (pode ser string vazia se padrão não configurada)
            )
            _logger.info(f"Wizard: Pesquisa iniciada com sucesso. Search ID: {search_id}")

            # Fecha o wizard após iniciar a pesquisa
            # Opcional: pode redirecionar para a view da pesquisa criada se desejar
            # return {
            #     'type': 'ir.actions.act_window',
            #     'res_model': 'pesquisa_aiia.search',
            #     'res_id': search_id,
            #     'view_mode': 'form',
            #     'target': 'current', # Abre na mesma aba
            # }
            return {'type': 'ir.actions.act_window_close'}

        except (UserError, ValidationError) as e:
            # Repassa erros de validação ou UserErrors vindos de start_new_search
            _logger.warning(f"Wizard: Erro de validação/usuário ao iniciar pesquisa: {e}")
            raise e
        except Exception as e:
            # Captura outros erros inesperados
            _logger.exception(f"Wizard: Erro inesperado ao iniciar pesquisa: {e}")
            raise UserError(_("Ocorreu um erro inesperado ao tentar iniciar a pesquisa. Contacte o administrador ou verifique os logs do sistema."))