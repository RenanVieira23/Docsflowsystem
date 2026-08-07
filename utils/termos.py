"""
utils/termos.py
================
Termos de Uso e Política de Privacidade (LGPD) — DocsFlow System.

⚠️ IMPORTANTE: o texto abaixo é um MODELO tecnicamente orientado pela
LGPD (Lei 13.709/2018), mas contém placeholders entre colchetes (ex:
[RAZÃO SOCIAL], [CNPJ], [E-MAIL DO ENCARREGADO]) que precisam ser
preenchidos com os dados reais da empresa. Recomenda-se revisão por
um advogado antes de publicar em produção.

VERSIONAMENTO: sempre que o conteúdo abaixo for alterado de forma
relevante, incremente VERSAO_TERMOS_ATUAL (ex: "1.0" -> "1.1"). Isso
faz com que TODOS os usuários — mesmo os que já haviam aceitado uma
versão anterior — sejam obrigados a aceitar a nova versão no próximo
login (ver pages/login/view.py e database/models.py ->
registrar_aceite_termos).
"""

VERSAO_TERMOS_ATUAL = "1.0"


def precisa_aceitar_termos(usuario: dict) -> bool:
    """
    Retorna True se o usuário ainda não aceitou a versão vigente dos
    termos — seja por nunca ter aceitado nenhuma versão (cadastro
    anterior a esta funcionalidade), seja por a versão aceita estar
    desatualizada.
    """
    if not usuario:
        return True
    versao_aceita = usuario.get("termos_versao")
    return versao_aceita != VERSAO_TERMOS_ATUAL


TEXTO_TERMOS_USO = """
# Termos de Uso — DocsFlow System

**Versão 1.0 — vigente a partir de [DATA DE PUBLICAÇÃO]**

## 1. Identificação

Estes Termos de Uso regem a utilização do sistema **DocsFlow System**
("Sistema"), plataforma de gestão de documentos, contratos e prazos,
fornecida por **[RAZÃO SOCIAL DA EMPRESA]**, inscrita no CNPJ sob o
nº **[CNPJ]**, com sede em **[ENDEREÇO]** ("DocsFlow", "nós").

## 2. Aceitação

Ao acessar ou utilizar o Sistema, você declara que leu, compreendeu e
concorda integralmente com estes Termos de Uso e com a Política de
Privacidade. Caso não concorde, não utilize o Sistema.

Se você está utilizando o Sistema em nome de uma pessoa jurídica
(escritório de advocacia, departamento jurídico ou empresa
"Contratante"), você declara ter poderes para vinculá-la a estes
Termos.

## 3. Objeto do Sistema

O DocsFlow System oferece funcionalidades de cadastro e gestão de
clientes, contratos, partes vinculadas, prazos, alertas e relatórios,
organizados de forma isolada por Contratante ("multi-tenant"), com
controle de acesso por cargo e permissões.

## 4. Cadastro e Responsabilidades do Usuário

4.1. O acesso ao Sistema é concedido mediante cadastro individual,
associado a um e-mail e senha. Cada usuário é responsável por manter
a confidencialidade de suas credenciais e por todas as atividades
realizadas em sua conta.

4.2. É responsabilidade do usuário e da Contratante:
   - Garantir a veracidade e a licitude dos dados inseridos no Sistema;
   - Possuir base legal adequada (LGPD) para inserir dados pessoais de
     terceiros (clientes, partes contratuais) no Sistema;
   - Notificar imediatamente a DocsFlow em caso de uso não autorizado
     da conta ou suspeita de violação de segurança;
   - Utilizar o Sistema em conformidade com a legislação vigente,
     incluindo normas de sigilo profissional aplicáveis (quando
     utilizado por advogados/escritórios).

4.3. A DocsFlow poderá suspender ou encerrar contas que violem estes
Termos, mediante notificação prévia sempre que possível.

## 5. Papéis em Relação aos Dados Pessoais (LGPD)

5.1. Em relação aos dados pessoais de clientes, partes e terceiros
inseridos pela Contratante no Sistema (ex: nome, CPF/CNPJ de partes
contratuais), a **Contratante atua como Controladora** dos dados, nos
termos do art. 5º, VI da LGPD, e a **DocsFlow atua como Operadora**,
tratando esses dados exclusivamente conforme as instruções da
Contratante e para os fins de prestação do Sistema.

5.2. Em relação aos dados cadastrais dos próprios usuários da
plataforma (nome, e-mail, registros de acesso e uso do Sistema), a
**DocsFlow atua como Controladora**, nos termos descritos na Política
de Privacidade.

## 6. Propriedade Intelectual

O Sistema, seu código-fonte, layout, marca e demais elementos são de
propriedade da DocsFlow (ou licenciados a ela), sendo vedada a
reprodução, engenharia reversa ou distribuição não autorizada.

## 7. Disponibilidade e Suporte

7.1. A DocsFlow envidará esforços razoáveis para manter o Sistema
disponível, podendo realizar manutenções programadas com aviso
prévio, quando possível.

7.2. O Sistema é fornecido "como está". Na máxima extensão permitida
pela legislação aplicável (incluindo o Código de Defesa do
Consumidor, quando aplicável), a DocsFlow não garante disponibilidade
ininterrupta e não se responsabiliza por danos indiretos decorrentes
de indisponibilidade eventual, ressalvados os casos de dolo ou culpa
grave.

## 8. Limitação de Responsabilidade

A DocsFlow não se responsabiliza pela exatidão, licitude ou adequação
dos dados e documentos inseridos pelos usuários, sendo estes de
inteira responsabilidade de quem os insere. Prazos, alertas e
cálculos automáticos gerados pelo Sistema são ferramentas de apoio e
não substituem a conferência e o julgamento profissional do usuário.

## 9. Vigência e Rescisão

Estes Termos vigoram enquanto durar a relação contratual entre a
Contratante e a DocsFlow. O encerramento da conta poderá ocorrer a
pedido da Contratante ou por iniciativa da DocsFlow, nos casos
previstos nestes Termos ou no contrato de prestação de serviço
celebrado entre as partes.

## 10. Alterações destes Termos

Estes Termos poderão ser atualizados periodicamente. Alterações
relevantes serão comunicadas e exigirão novo aceite antes da
continuidade do uso do Sistema.

## 11. Legislação Aplicável e Foro

Estes Termos são regidos pelas leis da República Federativa do
Brasil. Fica eleito o foro da comarca de **[FORO]** para dirimir
quaisquer controvérsias, com renúncia a qualquer outro, por mais
privilegiado que seja.

## 12. Contato

Dúvidas sobre estes Termos podem ser enviadas para **[E-MAIL DE CONTATO]**.
"""


TEXTO_POLITICA_PRIVACIDADE = """
# Política de Privacidade — DocsFlow System

**Versão 1.0 — vigente a partir de [DATA DE PUBLICAÇÃO]**

Esta Política descreve como a **DocsFlow** trata dados pessoais no
contexto do Sistema, em conformidade com a Lei nº 13.709/2018 (LGPD).

## 1. Dados Tratados

### 1.1. Dados dos usuários da plataforma (Controladora: DocsFlow)
Nome, e-mail, cargo/função no sistema, registros de acesso (data,
hora, ações realizadas) e dados técnicos de sessão, coletados para
fins de autenticação, controle de acesso e segurança.

### 1.2. Dados inseridos pela Contratante (Operadora: DocsFlow)
Dados de clientes, partes contratuais e documentos inseridos pela
Contratante no exercício de sua própria atividade (ex: nome, CPF/CNPJ,
dados contratuais), tratados pela DocsFlow exclusivamente conforme
instruções da Contratante, nos termos do item 5 dos Termos de Uso.

## 2. Finalidade e Base Legal

Os dados descritos no item 1.1 são tratados com base na **execução de
contrato** (art. 7º, V, LGPD) — viabilizar o acesso e uso do Sistema
— e no **legítimo interesse** (art. 7º, IX) para fins de segurança,
prevenção a fraudes e melhoria do Sistema.

Os dados descritos no item 1.2 são tratados exclusivamente conforme a
base legal definida pela própria Contratante, como Controladora
desses dados.

## 3. Compartilhamento de Dados

3.1. Os dados podem ser processados por fornecedores de infraestrutura
tecnológica (ex: hospedagem em nuvem e banco de dados via Supabase,
Inc.), que atuam como suboperadores, sujeitos a obrigações
contratuais de confidencialidade e segurança.

3.2. A DocsFlow não vende, aluga ou compartilha dados pessoais com
terceiros para fins de marketing.

3.3. Dados poderão ser divulgados quando exigido por lei, ordem
judicial ou autoridade competente.

## 4. Segurança da Informação

Adotamos medidas técnicas e administrativas para proteger os dados
pessoais, incluindo:
   - Isolamento de dados por Contratante (arquitetura multi-tenant
     com controle de acesso via Row Level Security);
   - Controle de acesso por cargo e permissões individuais;
   - Criptografia em trânsito (HTTPS/TLS);
   - Registro de auditoria de ações relevantes no Sistema.

Nenhum sistema é absolutamente livre de risco. Em caso de incidente
de segurança que possa acarretar risco relevante aos titulares, a
DocsFlow comunicará a Contratante e, quando aplicável, a Autoridade
Nacional de Proteção de Dados (ANPD), nos prazos legais.

## 5. Retenção e Eliminação

Os dados são mantidos pelo período necessário ao cumprimento das
finalidades descritas nesta Política, ou pelo prazo exigido por
obrigações legais ou regulatórias (ex: prazos prescricionais
aplicáveis a contratos e documentos jurídicos), podendo ser eliminados
ou anonimizados após esse período, mediante solicitação da
Contratante ou por rotina de descarte.

## 6. Direitos do Titular

Nos termos do art. 18 da LGPD, o titular de dados pessoais pode
solicitar, mediante requisição ao encarregado indicado no item 8:
confirmação da existência de tratamento; acesso aos dados; correção
de dados incompletos, inexatos ou desatualizados; anonimização,
bloqueio ou eliminação de dados desnecessários; portabilidade;
eliminação de dados tratados com consentimento; informação sobre
compartilhamento; e revogação do consentimento, quando aplicável.

Quando o titular for cliente ou parte contratual cadastrada por uma
Contratante (item 1.2), a solicitação deve ser dirigida
preferencialmente à própria Contratante, na qualidade de Controladora
desses dados.

## 7. Cookies e Dados de Navegação

O Sistema utiliza dados de sessão estritamente necessários ao seu
funcionamento (autenticação e manutenção de sessão). Não utilizamos
cookies de rastreamento de terceiros para fins publicitários.

## 8. Encarregado de Dados (DPO)

Para exercer seus direitos ou esclarecer dúvidas sobre esta Política,
entre em contato com nosso Encarregado de Proteção de Dados:
**[NOME DO ENCARREGADO] — [E-MAIL DO ENCARREGADO/DPO]**.

## 9. Alterações desta Política

Esta Política poderá ser atualizada periodicamente. Alterações
relevantes serão comunicadas e exigirão novo aceite antes da
continuidade do uso do Sistema.
"""