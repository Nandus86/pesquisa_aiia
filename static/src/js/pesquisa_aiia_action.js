/** @odoo-module **/
import { registry } from "@web/core/registry";
// Ajuste o caminho se a estrutura for diferente
import { PesquisaAiiaSearchComponent } from "@pesquisa_aiia/components/pesquisa_aiia_search_component/pesquisa_aiia_search_component";

registry.category("actions").add("pesquisa_aiia.action_client_search", PesquisaAiiaSearchComponent);