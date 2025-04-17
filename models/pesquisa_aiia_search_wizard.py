# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PesquisaAiiaSearchWizard(models.TransientModel):
    _name = 'pesquisa_aiia.search.wizard'
    _description = 'Assistente para Iniciar Nova Pesquisa AIIA'

    search_query = fields.Char(string='Termo da Pesquisa', required=True)

    def action_start_search(self):
        self.ensure_one()
        if not self.search_query:
            raise UserError(_("Por favor, informe um termo para pesquisar."))

        try:
            # Chama o método que já existe no modelo principal
            search_id = self.env['pesquisa_aiia.search'].start_new_search(self.search_query)
            _logger.info(f"Pesquisa iniciada via Wizard. Search ID: {search_id}") # Adicione logger se não tiver

            # Opcional: retornar ação para abrir a pesquisa criada ou a lista
            # Por enquanto, apenas fecha o wizard
            return {'type': 'ir.actions.act_window_close'}

        except (UserError, ValidationError) as e:
            raise e # Repassa erros conhecidos
        except Exception as e:
            # Logue o erro inesperado
            _logger.exception(f"Erro inesperado ao iniciar pesquisa via Wizard: {e}")
            raise UserError(_("Ocorreu um erro inesperado ao iniciar a pesquisa. Verifique os logs."))