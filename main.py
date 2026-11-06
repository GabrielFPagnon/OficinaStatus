import os
import httpx
from fastapi import FastAPI, Request, Header, Response, BackgroundTasks, Depends
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from banco import get_db
from sqlalchemy import select, Update
from datetime import datetime
from models import CanalUsuario, Mensagem, PlataformaMsg, StatusMsg, Etapa, OrdemServico

load_dotenv()

app = FastAPI()
SEGREDO = os.getenv("TELEGRAM_WEBHOOK_SECRET")
TOKEN = os.getenv("TELEGRAM_TOKEN")

################################################ Funções #######################################################################################

async def enviar_mensagem_telegram(chat_id: str, texto: str, canal_id: int, db: AsyncSession, botoes: list = None):
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}
    
    if botoes:
        payload["reply_markup"] = {"inline_keyboard": [botoes]}
        
    async with httpx.AsyncClient() as client:
        res = await client.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload)
        dados = res.json()
        
        if dados.get("ok"):
            id_externo = str(dados["result"]["message_id"])
            nova_msg = Mensagem(
                plataforma=PlataformaMsg.telegram,
                canal_usuario_id=canal_id,
                direcao="saida",
                id_externo=id_externo,
                conteudo=texto,
                status=StatusMsg.enviada, # Registra o envio com sucesso
                payload_bruto=dados
            )
            db.add(nova_msg)
            await db.commit()
            return True
        return False

async def processar_update(update: dict, db: AsyncSession):
    
    # Verifica se é uma MENSAGEM DE TEXTO normal
    if "message" in update:
        msg = update["message"]
        chat_id = str(msg["chat"]["id"])
        texto = msg.get("text", "")
        id_externo = str(msg.get("message_id", ""))
        
        canal_id = None

        # Trata o vinculo com o cliente.
        if texto.startswith("/start cliente_"):
            try:
                cliente_id = int(texto.split("_")[1])
                
                # Verifica se já existe um canal de conversa.
                stmt = select(CanalUsuario).where(
                    CanalUsuario.chat_id == chat_id, 
                    CanalUsuario.plataforma == PlataformaMsg.telegram
                )
                canal_existente = (await db.execute(stmt)).scalar_one_or_none()
                
                if not canal_existente:
                    novo_canal = CanalUsuario(
                        usuario_id=cliente_id,
                        plataforma=PlataformaMsg.telegram,
                        chat_id=chat_id,
                        codigo_convite=texto
                    )
                    db.add(novo_canal)
                    await db.flush() 
                    canal_id = novo_canal.id
                    print(f"Vínculo criado para o cliente {cliente_id}!")
                else:
                    canal_id = canal_existente.id
                    
            except Exception as e:
                print(f"Erro ao vincular cliente: {e}")
                
        else:
            # Tratamento de cliente com canal aberto.
            stmt = select(CanalUsuario).where(CanalUsuario.chat_id == chat_id, CanalUsuario.plataforma == PlataformaMsg.telegram)
            canal_existente = (await db.execute(stmt)).scalar_one_or_none()
            if canal_existente:
                canal_id = canal_existente.id

        # Registro de todas as mensagem no banco.
        nova_msg = Mensagem(
            plataforma=PlataformaMsg.telegram,
            canal_usuario_id=canal_id,
            direcao="entrada",
            id_externo=id_externo,
            conteudo=texto,
            status=StatusMsg.respondida, # Mensagem do usuário
            payload_bruto=update
        )
        db.add(nova_msg)
        await db.commit()
        print(f"Mensagem salva no banco: {texto}")

    # Callback Query (verifica o clique no botão)
    elif "callback_query" in update:
        cq = update["callback_query"]
        chat_id = str(cq["message"]["chat"]["id"])
        dados_botao = cq["data"] 
        
        # Responde ao Telegram para o botão parar de girar no celular[cite: 7]
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", 
                json={"callback_query_id": cq["id"], "text": "Resposta registrada!"}
            )
        
        print(f" Cliente clicou no botão: {dados_botao}")

        stmt_update = (
            update(Mensagem)
            .where(Mensagem.id_externo == str(cq["message"]["message_id"]))
            .values(status=StatusMsg.respondida, respondida_em=datetime.now())
        )
        await db.execute(stmt_update)
        await db.commit()
        print("Status da mensagem atualizado para 'respondida' no banco!")

@app.post("/webhook/telegram")
async def telegram_webhook(
    req: Request,
    bg: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(None),
    db: AsyncSession = Depends(get_db)
):
    # Validação de segurança.
    if x_telegram_bot_api_secret_token != SEGREDO:
        return Response(status_code=401, content="Assinatura inválida")

    # Recebe o payload do telegram.
    update = await req.json()

    # Processamento em segundo plano.
    bg.add_task(processar_update, update, db)

    return Response(status_code=200)

from pydantic import BaseModel
import httpx
from models import Cliente, Veiculo

############################################# Schemas de Validação #######################################################

class ClienteCreate(BaseModel):
    nome: str
    telefone: str

class VeiculoCreate(BaseModel):
    cliente_id: int
    placa: str
    codigo_marca: str 
    codigo_modelo: str 
    codigo_ano: str 

class EtapaCreate(BaseModel):
    ordem_servico_id: int
    nome_etapa: str 

class OrdemServicoCreate(BaseModel):
    veiculo_id: int
    descricao: str

###################################################### Rotas #####################################################################

@app.post("/clientes/")
async def criar_cliente(cliente: ClienteCreate, db: AsyncSession = Depends(get_db)):
    novo_cliente = Cliente(nome=cliente.nome, telefone=cliente.telefone)
    db.add(novo_cliente)
    await db.commit()
    await db.refresh(novo_cliente)
    
    # Gera o Deep Link.
    link_bot = f"https://t.me/{os.getenv('TELEGRAM_BOT_USERNAME', 'SEU_BOT')}?start=cliente_{novo_cliente.id}"
    
    return {"cliente": novo_cliente, "link_vincular_telegram": link_bot}

@app.post("/veiculos/")
async def criar_veiculo(veiculo: VeiculoCreate, db: AsyncSession = Depends(get_db)):
    # Consulta a Segunda API FIPE Parallelum
    url_fipe = f"https://parallelum.com.br/fipe/api/v1/carros/marcas/{veiculo.codigo_marca}/modelos/{veiculo.codigo_modelo}/anos/{veiculo.codigo_ano}"
    
    async with httpx.AsyncClient() as client:
        # Passando um User-Agent, evita bloqueio do Cloudflare.
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = await client.get(url_fipe, headers=headers)
        
        if resp.status_code != 200:
            print(f"Erro FIPE: {resp.status_code} - {resp.text}")
            return Response(status_code=400, content=f"Erro FIPE: {resp.text}")
            
        dados_fipe = resp.json()

    # Salva o veículo com o valor de referência FIPE.
    novo_veiculo = Veiculo(
        cliente_id=veiculo.cliente_id,
        placa=veiculo.placa,
        marca=dados_fipe.get("Marca", "Desconhecida"),
        modelo=dados_fipe.get("Modelo", "Desconhecido"),
        ano=int(dados_fipe.get("AnoModelo", 0)),
        valor_referencia=dados_fipe.get("Valor", "R$ 0,00")
    )
    db.add(novo_veiculo)
    await db.commit()
    await db.refresh(novo_veiculo)
    
    return novo_veiculo

@app.post("/ordens-servico/")
async def criar_ordem_servico(os_data: OrdemServicoCreate, db: AsyncSession = Depends(get_db)):
    # Cria a OS vinculada ao veículo existente
    nova_os = OrdemServico(  
        veiculo_id=os_data.veiculo_id,
        descricao=os_data.descricao
    )
    db.add(nova_os)
    await db.commit()
    await db.refresh(nova_os)
    
    return nova_os

@app.post("/etapas/")
async def avanca_etapa(etapa: EtapaCreate, db: AsyncSession = Depends(get_db)):
    nova_etapa = Etapa(ordem_servico_id=etapa.ordem_servico_id, nome=etapa.nome_etapa)
    db.add(nova_etapa)
    await db.commit()

    # Busca o chat_id do cliente dono da ordem de serviço
    stmt = select(CanalUsuario).order_by(CanalUsuario.id.desc()).limit(1)
    canal = (await db.execute(stmt)).scalar_one_or_none()

    if canal:
        texto = f"Sua ordem de serviço mudou para o status: <b>{etapa.nome_etapa}</b>"
        botoes = None
        
        if etapa.nome_etapa.lower() == "orçamento":
            texto = "Seu orçamento ficou pronto e o valor é R$ 500,00. Podemos iniciar?"
            # Envia botões interativos [cite: 4]
            botoes = [
                {"text": "Aprovar", "callback_data": f"os:{etapa.ordem_servico_id}:aprovar"},
                {"text": "Recusar", "callback_data": f"os:{etapa.ordem_servico_id}:recusar"}
            ]
            
        await enviar_mensagem_telegram(canal.chat_id, texto, canal.id, db, botoes)
        
    return {"status": "Etapa registrada e cliente notificado"}