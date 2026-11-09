# BarberFlow
Sistema de agendamento para uma barbearia com um barbeiro, área pública e painel administrativo.

## Requisitos
- Python 3.10 ou superior
- VS Code (opcional)

## Instalação no Windows
1. Extraia o ZIP e abra a pasta `barberflow` no VS Code.
2. Abra o terminal na pasta do projeto.
3. Crie um ambiente virtual:
   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   Se o PowerShell bloquear a ativação, use ` .venv\Scripts\activate.bat ` no CMD.
4. Instale as dependências:
   ```powershell
   py -m pip install -r requirements.txt
   ```
5. Inicie o sistema:
   ```powershell
   py app.py
   ```
6. Abra `http://127.0.0.1:5000`.

O banco SQLite `instance/barberflow.db` é criado automaticamente no primeiro início, com serviços de demonstração e usuário administrador inicial:
- Usuário: `admin`
- Senha: `BarberFlow@2026!`

**Entre no painel e altere a senha imediatamente** em “Alterar senha”. Não publique o sistema com a chave secreta ou senha padrão. Para produção, defina `SECRET_KEY`, `ADMIN_USER` e `ADMIN_PASSWORD` como variáveis de ambiente e use um servidor WSGI apropriado, HTTPS e PostgreSQL.

## Configuração inicial
No painel administrativo:
- **Serviços:** ajuste nomes, preços, descrições e duração.
- **Configurações:** defina nome da barbearia, expediente, dias de atendimento, datas fechadas, WhatsApp e chave PIX.
- **Agenda:** altere o status dos atendimentos para concluído, faltou ou cancelado.
- **Relatórios:** confira o total dos atendimentos concluídos no mês.

O número de WhatsApp deve ser informado com código do país e DDD, somente números (ex.: `5581999999999`). A chave PIX é exibida na confirmação quando o cliente escolhe PIX; a validação do pagamento é manual nesta versão.

## Regras da agenda
- Um único profissional, portanto não existem duas agendas separadas.
- O sistema consulta a duração do serviço e impede sobreposição de reservas ativas.
- Horários são oferecidos dentro do expediente e em intervalos configuráveis.
- Datas passadas, dias não úteis e datas fechadas não são aceitos.

## Observações importantes antes de publicar
Esta é uma primeira versão funcional para desenvolvimento e testes. Para uso público, recomenda-se acrescentar limitação de tentativas no login, proteção CSRF, política de privacidade/consentimento LGPD, backups automáticos, envio de confirmação automatizado, validação de telefone, logs e implantação com HTTPS. O botão WhatsApp abre uma mensagem pronta; não envia mensagens automaticamente.


## Personalizar a página inicial

A página inicial foi organizada para apresentar a barbearia de forma minimalista: banner fotográfico, botão de agendamento, área do Instagram e localização. O formulário de agendamento fica em uma página separada.

Para configurar as informações exibidas ao público:
1. Entre no painel administrativo.
2. Abra **Configurações**.
3. Informe o link completo do Instagram (por exemplo, `https://www.instagram.com/suabarbearia/`).
4. Informe o endereço completo, incluindo rua, número, bairro e cidade.
5. Salve. O mapa e o botão de rota serão montados a partir desse endereço.

A foto do banner é carregada de uma imagem hospedada no Unsplash; portanto, a primeira visualização da imagem depende de conexão com a internet. A incorporação do Instagram pode variar conforme as permissões e limitações definidas pela própria plataforma; o link para abrir o perfil permanece disponível.


## Novas funções — área do cliente e notificações
- Após reservar, o cliente recebe um link privado para consultar o histórico de agendamentos associados ao mesmo telefone.
- No link privado, pode cancelar ou remarcar agendamentos confirmados com pelo menos 12 horas de antecedência.
- O horário é validado novamente antes de cancelar/remarcar; horários cancelados voltam a ficar disponíveis.
- O painel administrativo registra novos agendamentos, cancelamentos e remarcações e exibe notificações em tempo real via Flask-SocketIO.
- A lista também é atualizada periodicamente como alternativa caso a conexão em tempo real seja interrompida.
- O banco existente recebe uma migração aditiva para a coluna de link privado; os agendamentos antigos são preservados.

**Importante:** o link da área do cliente funciona como uma chave privada de acesso. Oriente os clientes a não compartilhá-lo. O prazo de 12 horas está definido no código (`timedelta(hours=12)`) e pode ser ajustado.


## Área do cliente
O cabeçalho público possui o botão **Meus cortes**. Após realizar um agendamento, o navegador mantém o acesso privado à área do cliente. Para acessar em outro dispositivo ou navegador, utilize o código/link privado apresentado na confirmação do agendamento. O cliente pode consultar o histórico e cancelar agendamentos com pelo menos 12 horas de antecedência; a opção de remarcar foi removida.
