/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount, useSubEnv } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { formatDateTime } from "@web/core/l10n/dates"; // Para formatar datas

export class PesquisaAiiaSearchComponent extends Component {
    static template = "pesquisa_aiia.PesquisaAiiaSearchComponent";

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.action = useService("action");
        // this.busService = useService("bus_service"); // Para refresh automático (futuro)

        this.searchInputRef = useRef("searchInput");

        this.state = useState({
            searchQueryInput: "",
            searchHistory: [], // Lista de {id, name, search_query, status, create_date, next_page_token}
            activeSearchId: null,
            searchResults: [], // Lista de {id, name, phone, email}
            isLoadingHistory: false,
            isLoadingResults: false,
            isSearching: false, // Bloqueia botões durante chamadas RPC
            lastError: null,
        });

         // Para acessar o registro ativo nos getters computados
        useSubEnv({
            get activeSearch() {
                return this.state.searchHistory.find(s => s.id === this.state.activeSearchId);
            }
        });


        onWillStart(async () => {
            await this.loadSearchHistory();
            // Tenta selecionar a mais recente automaticamente
            if (this.state.searchHistory.length > 0) {
                await this.selectSearch(this.state.searchHistory[0].id);
            }
        });

        onMounted(() => {
            this.focusInput();
            // TODO: Configurar BUS para refresh automático de resultados (mais avançado)
        });

         onWillUnmount(() => {
             // TODO: Remover listeners do BUS
         });
    }

    // Getter computado para o registro ativo
    get activeSearch() {
        return this.env.activeSearch;
    }


    // --- Carregamento de Dados ---
    async loadSearchHistory() {
        this.state.isLoadingHistory = true;
        try {
            this.state.searchHistory = await this.orm.searchRead(
                "pesquisa_aiia.search",
                [['user_id', '=', session.user_id]],
                ["id", "name", "search_query", "status", "create_date", "next_page_token"],
                { order: "create_date DESC" }
            );
        } catch (error) {
            this.handleError("Erro ao carregar histórico de pesquisas.", error);
        } finally {
            this.state.isLoadingHistory = false;
        }
    }

    async loadSearchResults(searchId) {
         if (!searchId) {
             this.state.searchResults = [];
             return;
         }
        this.state.isLoadingResults = true;
         this.state.searchResults = []; // Limpa antes de carregar
        try {
            this.state.searchResults = await this.orm.searchRead(
                "pesquisa_aiia.lead",
                [['search_id', '=', searchId]],
                ["id", "name", "phone", "email"], // Campos básicos para a lista
                { order: "create_date DESC" } // Ou outra ordem
            );
        } catch (error) {
            this.handleError(`Erro ao carregar resultados da pesquisa ${searchId}.`, error);
        } finally {
            this.state.isLoadingResults = false;
        }
    }

    // --- Ações do Usuário ---
    async selectSearch(searchId) {
        if (this.state.activeSearchId === searchId) return;
        this.state.activeSearchId = searchId;
        this.state.lastError = null; // Limpa erro ao mudar
        await this.loadSearchResults(searchId);
    }

    async startNewSearch() {
        const query = this.state.searchQueryInput.trim();
        if (!query || this.state.isSearching) return;

        this.state.isSearching = true;
        this.state.lastError = null;
        try {
            const result = await this.rpc("/pesquisa_aiia/rpc/start_search", { query: query });
            if (result.status === 'success' && result.search_id) {
                 this.notification.add(`Pesquisa por '${query}' iniciada!`, { type: 'success' });
                 this.state.searchQueryInput = ""; // Limpa input
                 await this.loadSearchHistory(); // Recarrega histórico
                 await this.selectSearch(result.search_id); // Seleciona a nova pesquisa
            } else {
                // Caso o backend retorne status error por algum motivo inesperado
                this.handleError(result.message || "Erro desconhecido ao iniciar pesquisa.");
            }
        } catch (error) {
             // Erros RPC (UserError, etc.) são tratados aqui
            this.handleError("Erro ao iniciar pesquisa.", error);
        } finally {
            this.state.isSearching = false;
            this.focusInput();
        }
    }

    async fetchNextPage() {
         const search = this.activeSearch;
         if (!search || !search.next_page_token || this.state.isSearching) return;

         this.state.isSearching = true;
         this.state.lastError = null;
         try {
             const result = await this.rpc("/pesquisa_aiia/rpc/search_next_page", { search_id: search.id });
              if (result.status === 'success') {
                  this.notification.add("Solicitação da próxima página enviada.", { type: 'info' });
                  // Atualiza o status localmente para 'processing' para feedback visual imediato
                  const searchIndex = this.state.searchHistory.findIndex(s => s.id === search.id);
                  if (searchIndex > -1) {
                       this.state.searchHistory[searchIndex].status = 'processing';
                       // Não remove o token aqui, o backend/webhook que vai fazer isso
                  }
              } else {
                   this.handleError(result.message || "Erro desconhecido ao solicitar próxima página.");
              }
         } catch (error) {
              this.handleError("Erro ao solicitar próxima página.", error);
         } finally {
              this.state.isSearching = false;
         }
    }

    openLead(leadId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'pesquisa_aiia.lead',
            res_id: leadId,
            views: [[false, 'form']], // Abre diretamente no formulário
            target: 'current', // Ou 'new' para pop-up
        });
    }

    // --- Handlers de Eventos ---
    handleInputKeydown(event) {
         if (event.key === "Enter" && !this.state.isSearching) {
             this.startNewSearch();
         }
     }

    // --- Utilidades ---
    formatDate(dateString) {
         if (!dateString) return "";
         // Adiciona 'Z' para indicar UTC e evitar problemas de timezone na formatação
         return formatDateTime(new Date(dateString + 'Z'), { size: 'short' });
    }

    focusInput() {
         setTimeout(() => {
             if (this.searchInputRef.el) {
                  this.searchInputRef.el.focus();
             }
         }, 50);
    }

     handleError(message, error = null) {
         let errorMessage = message;
         if (error) {
              console.error(message, error);
              // Tenta pegar a mensagem de erro do Odoo RPC Error
              const errorData = error.message?.data;
              errorMessage = errorData?.message || error.message || message;
         }
         this.state.lastError = errorMessage;
         this.notification.add(errorMessage, { type: 'danger' });
     }

}

// Logger Simples para Console do Navegador
// const _logger = {
//     info: (...args) => console.log("PesquisaAiiaComponent INFO:", ...args),
//     error: (...args) => console.error("PesquisaAiiaComponent ERROR:", ...args),
// };