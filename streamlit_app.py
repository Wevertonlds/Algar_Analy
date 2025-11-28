import streamlit as st
import pandas as pd
from datetime import datetime

# Importações dos módulos separados
from backend_service import (
    init_session, call_cortex_agent, 
    generate_insights, format_dataframe_display,
    extract_message_text, MESSAGES,
    save_feedback_to_snowflake,
    process_pending_feedback, process_agent_response, get_name_user,
    process_customer_vision, classify_user_intent,
    WELCOME_BOT_MESSAGE,
    extract_cpf_or_name_from_text, get_consultor_suggestions, save_conversation_log
)

from frontend_ui import (
    apply_custom_css, show_welcome_header, show_quick_links,
    show_sidebar_links, show_loaded_session_info, display_history_modal,
    exibir_cards_metricas, get_available_chart_types, create_advanced_visualization, show_feedback_input, 
    show_logo_insight_center, exibir_botao_dicas
)

def main():
    """Função principal da aplicação"""
    # 1) Configuração da página
    st.set_page_config(
        page_title="Analy - Assistente de Dados",
        layout="wide"
    )
    
    # 2) Aplica CSS customizado
    apply_custom_css()

    # 3) Conexão
    session, connected = init_session()
    if not connected:
        st.error(MESSAGES["connection_error"])
        st.stop()

    # 4) Inicializa estados de sessão
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "conversation_messages" not in st.session_state:
        st.session_state.conversation_messages = []

    if "agent_messages" not in st.session_state:
        st.session_state.agent_messages = []
    if "chart_theme" not in st.session_state:
        st.session_state.chart_theme = "plotly_white"
        
    # 5) Recupera nome do usuário autenticado
    username = st.user.email.upper()

    username_first = get_name_user(session, username)

    #username_first = st.user.email.split("@")[0].upper()
    
    # 5.1) Processa feedbacks pendentes
    process_pending_feedback(session, username)
    
    if len(st.session_state.messages) == 0:
        show_welcome_header(username_first)
        exibir_cards_metricas(session)
        show_quick_links()

    # 8) Sidebar: Links rápidos + histórico + controles
    with st.sidebar:
        show_logo_insight_center()
        show_sidebar_links()
        #if len(st.session_state.messages) != 0:

        st.markdown("---")
        if st.button("🔄 Nova Conversa", use_container_width=True, type="primary"):
            # Limpa todas as mensagens e estados relacionados
            st.session_state.messages = []
            if "agent_messages" in st.session_state:
                st.session_state.agent_messages = []
            if "session_loaded" in st.session_state:
                st.session_state["session_loaded"] = False
            if "loaded_session_info" in st.session_state:
                del st.session_state["loaded_session_info"]
            if "show_history" in st.session_state:
                st.session_state["show_history"] = False
            # Limpar session_id para iniciar nova sessão
            if "session_id" in st.session_state:
                del st.session_state["session_id"]

            st.success("Nova conversa iniciada! 🎉")
            st.rerun()
    
        
        st.markdown("### 📂 Histórico de Conversas")
        display_history_modal(session, username)
        
    # 9) Mostra informações de sessão carregada se houver
    show_loaded_session_info()
 
    # 10) =================================================
    # ÁREA DE CHAT
    # =================================================
        

    chat_container = st.container()
    
    # ---------- Rodapé ----------
    st.markdown(
        "<div style='text-align: right; font-size: 12px; color: gray;'>"
        "⚡ Powered by <b>Gerência de Dados & Analytics</b>"
        "</div>",
        unsafe_allow_html=True
    )
    
    with chat_container:
        messages_container = st.container()

        # ---------- Input do usuário ----------
        user_input = st.chat_input(MESSAGES["chat_placeholder"])
        
        # ---------- Botão de Exportar Conversa ----------
        # if len(st.session_state.messages) > 0:
        #     col1, col2, col3 = st.columns([1, 2, 1])
        #     with col2:
        #         if st.button("📄 Exportar Conversa", use_container_width=True, type="secondary"):
        #             with st.spinner("Gerando PDF da conversa..."):
        #                 pdf_buffer = export_conversation_to_pdf(st.session_state.messages, username_first)
                        
        #                 # Criar nome do arquivo com timestamp
        #                 timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        #                 filename = f"conversa_insight_center_{timestamp}.pdf"
                        
        #                 # Oferecer download
        #                 st.download_button(
        #                     label="📥 Baixar PDF",
        #                     data=pdf_buffer.getvalue(),
        #                     file_name=filename,
        #                     mime="application/pdf",
        #                     use_container_width=True
        #                 )
        #                 st.success("✅ PDF gerado com sucesso!")

        if user_input:
            st.session_state.messages.append({
                "role": "user",
                "content": [{"type": "text", "text": user_input}]
            })
            
            save_conversation_log(session, username, "user", user_input, thinking_log="")

            user_intent = classify_user_intent(session, user_input)
            
            # Extrai CPF/CNPJ/Nome do texto
            id_customer = extract_cpf_or_name_from_text(session, user_input)

            # Caso o usuário pesquise detalhamento de cliente por nome, vamos deixar o Agent processar
            if user_intent == "customer_details" and ('consultor' not in user_input):# and ("nome" not in id_customer):
                # Adicionar mensagem do usuário ao contexto do agent ANTES do processamento
                user_message = {
                    "role": "user",
                    "content": [{"type": "text", "text": user_input}]
                }
                st.session_state.agent_messages.append(user_message)

                with st.spinner(MESSAGES["search_visao"]):
                    processed_response = process_customer_vision(session, user_input, id_customer)

                if processed_response:
                    assistant_msg = {
                        "role": "assistant",
                        "content": processed_response["text"],
                        "timestamp": datetime.now(),
                        "data": processed_response.get("data", False)
                    }
                    st.session_state.messages.append(assistant_msg)

                    # Adicionar resposta do assistente ao contexto do agent
                    agent_assistant_msg = {
                        "role": "assistant",
                        "content": [{"type": "text", "text": processed_response["text"]}]
                    }
                    st.session_state.agent_messages.append(agent_assistant_msg)

                    has_data = processed_response.get("data", False) is not False
                    save_conversation_log(
                        session,
                        username,
                        "assistant",
                        processed_response["text"],
                        has_data=has_data,
                        assistant_msg_dict=assistant_msg,
                        thinking_log=""
                        )

                    st.rerun()

                else:
                    # Se não encontrou na visão, tenta via Cortex Agent
                    with st.spinner(MESSAGES["search_alternative"]):  # Nova mensagem para busca alternativa
                        response = call_cortex_agent(user_input)
                        processed_response = process_agent_response(session, user_input, response)
                    
            else:
                with st.spinner(MESSAGES["thinking"]):
                    response = call_cortex_agent(user_input)
                    processed_response = process_agent_response(session, user_input, response)

            # 4. Processar resposta (comum para ambos os caminhos)
            if processed_response["response_type"] == "invalid_response":
                assistant_msg = {
                    "role": "assistant",
                    "content": "",
                    "interpretation": processed_response["interpretation"],
                    "timestamp": datetime.now(),
                    "error": processed_response["error"]
                }
            elif processed_response["response_type"] == "error":
                assistant_msg = {
                    "role": "assistant",
                    "content": processed_response["text"] or MESSAGES["error"],
                    "timestamp": datetime.now(),
                    "error": processed_response["error"]
                }
            elif processed_response["response_type"] == "text_only":
                assistant_msg = {
                    "role": "assistant",
                    "content": processed_response["text"],
                    "timestamp": datetime.now()
                }
            elif processed_response["response_type"] in ["empty_data", "single_row", "multiple_rows", "sql_success", "data_only"]:
                assistant_msg = {
                    "role": "assistant",
                    "content": processed_response.get("text", ""),
                    "sql": processed_response.get("sql", ""),
                    "data": processed_response.get("data"),
                    "interpretation": processed_response.get("interpretation", ""),
                    "should_show_chart": processed_response.get("should_show_chart", False),
                    "chart": processed_response.get("chart"),
                    "insights": "",
                    "timestamp": datetime.now(),
                    "ordered": processed_response.get("ordered", False),
                    "order_sequence": processed_response.get("order_sequence", []),
                    "processed_response": processed_response
                }

            st.session_state.messages.append(assistant_msg)

            if assistant_msg.get("ordered", False):
                text_parts = []
                order_sequence = assistant_msg.get("order_sequence", [])
                processed_resp = assistant_msg.get("processed_response", {})

                for key in order_sequence:
                    if key.startswith("text_"):
                        text_content = processed_resp.get(key, "")
                        if text_content:
                            text_parts.append(text_content)

                assistant_text = "\n\n".join(text_parts) if text_parts else ""
                sql_query = ""  # SQL pode estar em sql_1, sql_2, etc - pegar o primeiro
                for key in order_sequence:
                    if key.startswith("sql_"):
                        sql_query = processed_resp.get(key, "")
                        break
            else:
                assistant_text = assistant_msg.get("content", "")
                sql_query = assistant_msg.get("sql", "")

            error_msg = assistant_msg.get("error", "")
            has_data = assistant_msg.get("data") is not None or assistant_msg.get("should_show_chart", False)

            # Determinar error_message baseado no response_type
            error_message_to_log = None
            if processed_response["response_type"] in ["error", "invalid_response"]:
                # Priorizar mensagem de 'error', depois 'content'
                error_message_to_log = (
                    assistant_msg.get("error") or 
                    assistant_msg.get("content") or 
                    "Erro não especificado"
                )

            save_conversation_log(
                session,
                username,
                "assistant",
                assistant_text,
                sql_query=sql_query if sql_query else None,
                has_data=has_data,
                error_message=error_message_to_log,
                assistant_msg_dict=assistant_msg,
                thinking_log=processed_response.get("thinking_log", "")
            )

            st.rerun()

        # -------------------------------------------------------------
        # RENDERIZAÇÃO DAS MENSAGENS
        # -------------------------------------------------------------

        with messages_container:
            if len(st.session_state.messages) == 0:

                ## Descomentar para ativar Dicas
                chat_header_col1, chat_header_col2 = st.columns([6, 1])
                
                with chat_header_col1:
                    st.markdown("#### 💬 Chat com a Analy")
                
                if WELCOME_BOT_MESSAGE:
                    with st.chat_message("assistant", avatar="analy_temp.png"):
                        st.write(WELCOME_BOT_MESSAGE)

                with chat_header_col2:
                    exibir_botao_dicas()

            for i, msg in enumerate(st.session_state.messages):
                with st.chat_message(msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "analy_temp.png"):
                    if msg["role"] == "user":
                        user_text = extract_message_text(msg["content"])
                        st.write(user_text)
                        continue

                    if msg.get("ordered", False):
                        # Modo ordenado - renderizar elementos na sequência
                        processed_resp = msg.get("processed_response", {})
                        order_sequence = msg.get("order_sequence", [])
                        
                        for elem_key in order_sequence:
                            elem_content = processed_resp.get(elem_key)
                            
                            if elem_key.startswith("text_"):
                                # Renderizar texto
                                st.write(elem_content)
                                
                            elif elem_key.startswith("chart_"):
                                # Renderizar gráfico Vega-Lite diretamente
                                if elem_content:
                                    try:
                                        import json
                                        chart_spec = json.loads(elem_content) if isinstance(elem_content, str) else elem_content
                                        st.vega_lite_chart(chart_spec, use_container_width=True)
                                    except Exception as e:
                                        st.error(f"Erro ao renderizar gráfico: {str(e)}")
                            
                            elif elem_key.startswith("table_"):
                                # Renderizar tabela
                                if elem_content and len(elem_content) > 0:
                                    df = pd.DataFrame(elem_content)
                                    with st.expander(f"📄 Dados ({len(df)} linhas)", expanded=True):
                                        display_df = format_dataframe_display(df.head(10))
                                        st.dataframe(display_df, use_container_width=True, height=300)
                                        
                                        if len(df) > 10:
                                            st.caption(f"Mostrando as primeiras 10 de {len(df)} linhas.")
                                            
                                            if st.checkbox(f"Ver mais linhas", key=f"more_rows_{i}_{elem_key}"):
                                                num_rows = st.slider(
                                                    "Número de linhas:",
                                                    min_value=10,
                                                    max_value=min(len(df), 1000),
                                                    value=10,
                                                    step=10,
                                                    key=f"slider_{i}_{elem_key}"
                                                )
                                                display_df_extended = format_dataframe_display(df.head(num_rows))
                                                st.dataframe(display_df_extended, use_container_width=True)
                                        
                                        # Botão de download CSV
                                        csv = df.to_csv(index=False).encode('utf-8')
                                        st.download_button(
                                            label="📥 Baixar CSV",
                                            data=csv,
                                            file_name=f"dados_{i}_{elem_key}.csv",
                                            mime="text/csv",
                                            key=f"download_{i}_{elem_key}"
                                        )
                        
                        # Mostrar erro se houver
                        if msg.get("error"):
                            st.error(msg["error"])
                        
                        # Mostrar interpretação se houver
                        if msg.get("interpretation"):
                            st.write(msg["interpretation"])
                    
                    else:
                        if msg.get("content"):
                            st.write(msg["content"])

                        # Mostrar erro se houver
                        if msg.get("error"):
                            st.write(msg["error"])
                        
                        # Mostrar interpretação se houver (para empty_data, single_row, ou multiple_rows sem gráfico)
                        if msg.get("interpretation") and not msg.get("error"):
                            st.write(msg['interpretation'])

                        if msg.get("data") is not None:
                            data = msg.get("data")
                            
                            if isinstance(data, list) and len(data) > 0:
                                df = pd.DataFrame(data)
                            
                            elif isinstance(data, pd.DataFrame):
                                df = data
                           
                            else:
                                df = pd.DataFrame()
                                st.error("Não foi possível criar DataFrame dos dados")
                            
                            if not df.empty:
                                # Verificar se deve mostrar gráfico
                                if msg.get("should_show_chart", False) and msg.get("chart"):
                                    try:
                                        import json
                                        # Se chart for uma lista (múltiplos gráficos)
                                        if isinstance(msg["chart"], list):
                                            for idx, chart_spec_str in enumerate(msg["chart"]):
                                                st.write(f"Gráfico {idx + 1}:")
                                                chart_spec = json.loads(chart_spec_str) if isinstance(chart_spec_str, str) else chart_spec_str
                                                st.vega_lite_chart(chart_spec, use_container_width=True)
                                        else:
                                            # Um único gráfico
                                            chart_spec = json.loads(msg["chart"]) if isinstance(msg["chart"], str) else msg["chart"]
                                            st.vega_lite_chart(chart_spec, use_container_width=True)
                                    except Exception as e:
                                        st.error(f"Erro ao renderizar gráfico: {str(e)}")
                                        st.code(f"Chart content: {msg['chart'][:200]}...")  # DEBUG
                                    
                                    # Container com botão e expander inline
                                    action_container = st.container()
                                    # with action_container:
                                    #     # Criar duas colunas com proporções ajustadas
                                    #     col1, col2 = st.columns([1, 1.2])
                                        
                                    #     with col1:
                                    #         insights_generated = msg.get("insights") is not None and msg.get("insights") != ""
                                    #         button_label = "✅ Insights Gerados" if insights_generated else "💡 Gerar Insights"
                                            
                                    #         if st.button(button_label, 
                                    #                     key=f"insight_btn_{i}", 
                                    #                     use_container_width=True,
                                    #                     disabled=insights_generated):
                                    #             with st.spinner(MESSAGES["generating_insights"]):
                                    #                 user_question = extract_message_text(
                                    #                     st.session_state.messages[i-1]["content"]
                                    #                 ) if i > 0 else ""
                                                    
                                    #                 insights = generate_insights(session, df, user_question)
                                    #                 st.session_state.messages[i]["insights"] = insights
                                    #                 st.rerun()
                                        
                                    #     with col2:
                                    # Expander estilizado para ficar alinhado
                                    with st.expander(f"📄 Ver Dados ({len(df)} linhas)", expanded=False):
                                        # Botão de download CSV
                                        csv = df.to_csv(index=False).encode('utf-8')
                                        st.download_button(
                                            label="📥 Baixar CSV",
                                            data=csv,
                                            file_name=f"dados_{i}.csv",
                                            mime="text/csv",
                                            key=f"download_{i}",
                                            help="Baixar CSV"
                                        )
                                        
                                        # Mostrar dados
                                        st.markdown("**📄 Dados:**")
                                        display_df = format_dataframe_display(df.head(10))
                                        st.dataframe(display_df, use_container_width=True, height=300)
                                        
                                        if len(df) > 10:
                                            st.caption(f"Mostrando as primeiras 10 de {len(df)} linhas.")
                                            
                                            # Slider para ver mais dados
                                            if st.checkbox("Ver mais linhas", key=f"more_rows_{i}"):
                                                num_rows = st.slider(
                                                    "Número de linhas:",
                                                    min_value=10,
                                                    max_value=min(len(df), 1000),
                                                    value=10,
                                                    step=10,
                                                    key=f"slider_{i}"
                                                )
                                                display_df_extended = format_dataframe_display(df.head(num_rows))
                                                st.dataframe(display_df_extended, use_container_width=True)
                                    
                                    # Exibir insights abaixo se já foram gerados
                                    if msg.get("insights"):
                                        st.markdown("---")
                                        st.markdown("### 💡 Insights Identificados")
                                        st.markdown(msg["insights"])
                                
                                else:
                                    # Quando não há gráfico, o expander pode ficar em largura total
                                    with st.expander(f"📄 Dados Detalhados ({len(df)} linhas)", expanded=True):
                                        display_df = format_dataframe_display(df.head(10))
                                        st.dataframe(display_df, use_container_width=True)
                                        
                                        if len(df) > 10:
                                            st.caption(f"Mostrando as primeiras 10 de {len(df)} linhas.")
                                            
                                            # Opção para ver mais dados
                                            if st.checkbox("Ver mais linhas", key=f"more_rows_no_chart_{i}"):
                                                num_rows = st.slider(
                                                    "Número de linhas:",
                                                    min_value=10,
                                                    max_value=min(len(df), 1000),
                                                    value=10,
                                                    step=10,
                                                    key=f"slider_no_chart_{i}"
                                                )
                                                display_df_extended = format_dataframe_display(df.head(num_rows))
                                                st.dataframe(display_df_extended, use_container_width=True)
                            else:
                                pass
                        else:
                            pass
                    
                    # ===== FEEDBACK PARA TODAS AS MENSAGENS DO ASSISTENTE =====
                    # Adicionar uma pequena separação visual
                    st.markdown("---")
                    
                    # Obter informações para o feedback
                    user_question = ""
                    if i > 0 and st.session_state.messages[i-1]["role"] == "user":
                        user_question = extract_message_text(st.session_state.messages[i-1]["content"])
                    
                    # Determinar o tipo de resposta para o feedback
                    response_type = "text"
                    if msg.get("ordered", False):
                        # Para modo ordenado, verificar se tem gráfico ou tabela
                        if any(k.startswith("chart_") for k in msg.get("order_sequence", [])):
                            response_type = "chart"
                        elif any(k.startswith("table_") for k in msg.get("order_sequence", [])):
                            response_type = "data_table"
                    else:
                        if msg.get("data") is not None:
                            if msg.get("should_show_chart", False):
                                response_type = "chart"
                            else:
                                response_type = "data_table"
                        elif msg.get("error"):
                            response_type = "error"
                    
                    # Exibir botões de feedback
                    show_feedback_input(
                        message_index=i,
                        graph_type=response_type,
                        sql_query=msg.get("sql", ""),
                        user_question=user_question
                    )
if __name__ == "__main__":
    main()
