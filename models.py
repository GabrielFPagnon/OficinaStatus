import enum
from sqlalchemy import Column, Integer, String, BigInteger, Boolean, ForeignKey, DateTime, Enum, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from banco import Base

class PlataformaMsg(enum.Enum):
    telegram = 'telegram'
    discord = 'discord'

class StatusMsg(enum.Enum):
    enfileirada = 'enfileirada'
    enviada = 'enviada'
    falha = 'falha'
    respondida = 'respondida'

class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    nome = Column(String, nullable=False)
    telefone = Column(String)

class Veiculo(Base):
    __tablename__ = "veiculos"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    cliente_id = Column(BigInteger, ForeignKey("clientes.id"), nullable=False)
    placa = Column(String, nullable=False, unique=True)
    marca = Column(String)
    modelo = Column(String)
    ano = Column(Integer)
    valor_referencia = Column(String) # Dados da segunda API (FIPE)[cite: 1]

class OrdemServico(Base):
    __tablename__ = "ordens_servico"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    veiculo_id = Column(BigInteger, ForeignKey("veiculos.id"), nullable=False)
    descricao = Column(String)
    criada_em = Column(DateTime(timezone=True), default=datetime.utcnow)

class Etapa(Base):
    __tablename__ = "etapas"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ordem_servico_id = Column(BigInteger, ForeignKey("ordens_servico.id"), nullable=False)
    nome = Column(String, nullable=False) # Ex: orcamento, aprovacao, execucao, pronto[cite: 1]
    notificado = Column(Boolean, default=False)
    criada_em = Column(DateTime(timezone=True), default=datetime.utcnow)

class CanalUsuario(Base):
    __tablename__ = "canais_usuario"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id = Column(BigInteger, ForeignKey("clientes.id"), nullable=False)
    plataforma = Column(Enum(PlataformaMsg, name="plataforma_msg"), nullable=False)
    chat_id = Column(String, nullable=False)
    codigo_convite = Column(String)
    ativo = Column(Boolean, nullable=False, default=True)
    vinculado_em = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint('plataforma', 'chat_id', name='uq_plataforma_chat'),)

class Mensagem(Base):
    __tablename__ = "mensagens"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    plataforma = Column(Enum(PlataformaMsg, name="plataforma_msg"), nullable=False)
    canal_usuario_id = Column(BigInteger, ForeignKey("canais_usuario.id"))
    direcao = Column(String, nullable=False)
    id_externo = Column(String)
    conteudo = Column(String, nullable=False)
    status = Column(Enum(StatusMsg, name="status_msg"), nullable=False, default=StatusMsg.enfileirada)
    erro_codigo = Column(String)
    erro_descricao = Column(String)
    payload_bruto = Column(JSONB)
    criada_em = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    enviada_em = Column(DateTime(timezone=True))
    respondida_em = Column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("direcao IN ('saida', 'entrada')", name="chk_direcao"),)