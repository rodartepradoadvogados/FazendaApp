# CONTRATO DE LICENÇA DE USO DE SOFTWARE, HOSPEDAGEM E SUPORTE TÉCNICO — SISTEMA COWDATA

Instrumento particular de prestação de serviços de tecnologia para gestão de fazenda leiteira.

Pelo presente instrumento particular, de um lado:

**{{ empresa_nome }}**, inscrita no CNPJ sob o nº {{ empresa_cnpj or "[PREENCHER — CNPJ a definir]" }}, com sede em {{ empresa_endereco or "[PREENCHER — endereço da sede]" }}, doravante denominada simplesmente **CONTRATADA**;

e de outro lado:

**{{ fazenda_nome }}**, inscrita no CPF/CNPJ sob o nº {{ fazenda_documento or "[PREENCHER]" }}, com endereço em {{ fazenda_endereco or "[PREENCHER]" }}, neste ato representada por {{ representante_nome or "[PREENCHER — nome do representante]" }}, portador(a) do CPF nº {{ representante_cpf or "[PREENCHER]" }}, doravante denominada simplesmente **CONTRATANTE**;

têm entre si justo e contratado o presente instrumento, que se rege pelas cláusulas seguintes.

## 1. DEFINIÇÕES

**1.1.** "Sistema" ou "CowData": plataforma de software como serviço (SaaS) para gestão de fazendas leiteiras, abrangendo os módulos de Rebanho, Reprodução, Sanidade, Produção, Financeiro, Estoque, Alimentação, Agricultura/Plantio e Consultor externo, conforme o plano contratado.

**1.2.** "Dados do Produtor": todo dado operacional, zootécnico, genético, produtivo, sanitário e financeiro inserido, gerado ou coletado no Sistema em razão do uso pela CONTRATANTE.

**1.3.** "Plataforma de Assinatura Eletrônica": serviço ZapSign, utilizado facultativamente para formalização de assinatura eletrônica deste e de outros instrumentos relacionados.

## 2. OBJETO

**2.1.** Licença de uso não exclusiva, não transferível e limitada ao número de fazendas/unidades contratadas, do Sistema CowData, incluindo hospedagem em nuvem, manutenção corretiva e evolutiva, atualizações e suporte técnico, nos termos e limites do plano contratado (Cláusula 4).

**2.2.** A licença não confere à CONTRATANTE qualquer direito sobre o código-fonte, a marca, o layout, a arquitetura ou quaisquer outros ativos de propriedade intelectual da CONTRATADA (Cláusula 8).

## 3. OBRIGAÇÕES DAS PARTES

**3.1. CONTRATADA:** manter o Sistema disponível em regime de melhores esforços; prestar suporte técnico em horário comercial; realizar cópias de segurança periódicas; zelar pela confidencialidade e integridade dos Dados do Produtor (Cláusula 6); comunicar manutenções programadas com antecedência razoável.

**3.2. CONTRATANTE:** efetuar o pagamento nas datas e formas ajustadas (Cláusula 5); fornecer informações verídicas; não ceder/compartilhar credenciais de acesso; utilizar o Sistema em conformidade com a legislação aplicável.

## 4. PLANOS, MÓDULOS E VALORES

**4.1.** A CONTRATANTE contrata o plano **{{ plano_nome }}**, no valor mensal de **R$ {{ preco_mensal }}**, compreendendo os módulos: {{ modulos_lista }}.

Tabela de planos: Standard R$ 250,00/mês (Rebanho, Reprodutivo) · Silver R$ 350,00/mês (+ Produtivo, Sanitário, Financeiro) · Gold R$ 420,00/mês (+ Planejamento, Pedidos, Estoque, Alimentação, Agricultura) · Diamond R$ 500,00/mês (+ Consultor externo).

**4.2. Periodicidade e desconto por pagamento antecipado:** a assinatura é mensal por padrão, cobrada via Pix Automático (recorrência autorizada uma única vez pela CONTRATANTE, Cláusula 5.1) ou boleto. Em pagamento adiantado: 5% no ciclo trimestral; 20% no ciclo semestral (exclusivo para pagamento via QR Code Pix dinâmico do período), sobre o valor mensal do plano. A CONTRATANTE optou pelo ciclo **{{ periodicidade }}**{% if desconto_pct %}, com desconto de **{{ desconto_pct }}%**, totalizando **R$ {{ valor_total_ciclo }}** no período{% endif %}.

**4.3.** Os valores serão reajustados anualmente pela variação acumulada do IPCA (ou índice que vier a substituí-lo).

## 5. FATURAMENTO E PAGAMENTO

**5.1.** Pagamento à escolha da CONTRATANTE: (a) Pix Automático, com autorização de débito recorrente concedida uma única vez pela CONTRATANTE, cobrança mensal automática; (b) QR Code Pix dinâmico avulso; ou (c) boleto bancário. Cobranças emitidas pela CONTRATADA via instituição de pagamento/financeira integrada ao Pix, regulada pelo Banco Central do Brasil.

**5.2.** Atraso superior a 10 dias corridos autoriza suspensão do acesso, mediante aviso prévio de 3 dias úteis, sem prejuízo de multa de 2%, juros de mora de 1% ao mês e correção monetária.

## 6. CONFIDENCIALIDADE, SEGREDO EMPRESARIAL E PROTEÇÃO DE DADOS (LGPD)

**6.1.** Os Dados do Produtor são de propriedade exclusiva da CONTRATANTE. A CONTRATADA não adquire qualquer direito de propriedade sobre tais dados.

**6.2.** Para os fins da Lei nº 13.709/2018 (LGPD), a CONTRATADA atua exclusivamente como **operadora**, e a CONTRATANTE como **controladora** dos Dados do Produtor.

**6.3.** A CONTRATADA se obriga a **não acessar, copiar, exportar, agregar, analisar ou utilizar** os Dados do Produtor para finalidade própria — incluindo desenvolvimento de produto, benchmarking setorial, comparação entre clientes ou uso comercial com concorrentes — sem autorização prévia, expressa, específica e por escrito da CONTRATANTE.

**6.4.** Os Dados do Produtor constituem também segredo de empresa nos termos do art. 195, incisos XI e XII, da Lei nº 9.279/1996.

**6.5. Acesso emergencial ("break-glass"):** só para (i) diagnóstico/correção de falhas técnicas, ou (ii) ordem judicial — com registro em log de auditoria (data, motivo, escopo, responsável) e comunicação à CONTRATANTE em até 5 dias úteis.

**6.6.** As obrigações desta cláusula sobrevivem à extinção do contrato, enquanto a CONTRATADA detiver qualquer Dado do Produtor.

## 7. ASSINATURA ELETRÔNICA

**7.1.** Este contrato pode ser assinado eletronicamente via ZapSign, com validade jurídica plena, nos termos do art. 10, §2º, da MP nº 2.200-2/2001.

**7.2.** Alternativamente, pode ser impresso, assinado fisicamente e devolvido digitalizado.

## 8. PROPRIEDADE INTELECTUAL

**8.1.** O Sistema, código-fonte, layout, schema do banco de dados, marcas e nome comercial permanecem de propriedade exclusiva da CONTRATADA.

## 9. DISPONIBILIDADE E LIMITAÇÃO DE RESPONSABILIDADE

**9.1.** Melhores esforços, sem garantia de disponibilidade ininterrupta de 100%.

**9.2.** A CONTRATADA não se responsabiliza por decisões zootécnicas, sanitárias, reprodutivas ou financeiras tomadas com base no Sistema.

## 10. VIGÊNCIA, RENOVAÇÃO E RESCISÃO

**10.1.** Vigência a partir da assinatura, prazo indeterminado, renovação automática a cada ciclo de faturamento.

**10.2.** Rescisão imotivada mediante aviso prévio de 30 dias, sem multa, ressalvados valores já devidos.

**10.3. Portabilidade dos dados:** exportação integral dos Dados do Produtor em até 15 dias corridos do pedido; exclusão definitiva em até 90 dias após a exportação, salvo obrigação legal de retenção.

## 11. DISPOSIÇÕES GERAIS

**11.1.** Vedada cessão sem consentimento prévio por escrito, ressalvada reorganização societária da CONTRATADA que preserve as obrigações.

**11.2.** Tolerância não implica novação ou renúncia de direitos.

**11.3.** Comunicações válidas por escrito, inclusive por e-mail, aos endereços de contato cadastrados no Sistema.

## 12. FORO

**12.1.** Foro da comarca de {{ cidade_foro or "[PREENCHER — comarca]" }}, {{ estado_foro or "[PREENCHER]" }}, com renúncia a qualquer outro.

---

{{ cidade_foro or "[Cidade]" }}, {{ data_hoje }}.

**{{ empresa_nome }}** — CONTRATADA

**{{ fazenda_nome }}** — CONTRATANTE
