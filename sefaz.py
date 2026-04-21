import threading
from dataclasses import dataclass, field
from typing import Callable, Optional
from lxml import etree

try:
    from pynfe.processamento.comunicacao import ComunicacaoSefaz
    from pynfe.utils.descompactar import DescompactaGzip
    from pynfe.utils.flags import NAMESPACE_NFE
    PYNFE_AVAILABLE = True
except ImportError:
    PYNFE_AVAILABLE = False


NS = {'ns': 'http://www.portalfiscal.inf.br/nfe'}

TIPO_SCHEMA = {
    'procNFe_v4.00.xsd': 'NF-e Completa',
    'resNFe_v1.01.xsd': 'Resumo NF-e',
    'procEventoNFe_v1.00.xsd': 'Evento NF-e',
}

CSTAT_MSGS = {
    '137': 'Nenhum documento encontrado',
    '138': 'Documentos encontrados',
}


TIPO_EVENTO = {
    '110111': 'Cancelamento',
    '110112': 'Cancelamento por substituição',
    '110110': 'Carta de Correção',
    '210200': 'Confirmação da Operação',
    '210210': 'Ciência da Operação',
    '210220': 'Desconhecimento da Operação',
    '210240': 'Operação não Realizada',
}


@dataclass
class Documento:
    nsu: str
    tipo: str
    schema: str
    chave: str = ''
    chave_ref: str = ''   # chave da NF-e referenciada (em eventos)
    tipo_evento: str = '' # código tpEvento (ex: '110111')
    xml_raw: str = ''
    emitente: str = ''
    destinatario: str = ''
    valor: str = ''
    data_emissao: str = ''
    status: str = 'OK'


@dataclass
class ResultadoConsulta:
    documentos: list = field(default_factory=list)
    ult_nsu: str = '0'
    max_nsu: str = '0'
    cstat: str = ''
    xmotivo: str = ''
    erro: Optional[str] = None


def _xpath_text(elemento, path, ns=NS, default=''):
    resultado = elemento.xpath(path, namespaces=ns)
    return resultado[0].text if resultado else default


def _parse_nfe_completa(xml_elemento) -> dict:
    ns_nfe = NS
    dados = {}
    try:
        dados['chave'] = _xpath_text(xml_elemento, '//ns:infNFe/@Id', ns_nfe) or ''
        if dados['chave'].startswith('NFe'):
            dados['chave'] = dados['chave'][3:]
        dados['emitente'] = (
            _xpath_text(xml_elemento, '//ns:emit/ns:xNome', ns_nfe) or
            _xpath_text(xml_elemento, '//ns:emit/ns:CNPJ', ns_nfe)
        )
        dados['destinatario'] = (
            _xpath_text(xml_elemento, '//ns:dest/ns:xNome', ns_nfe) or
            _xpath_text(xml_elemento, '//ns:dest/ns:CNPJ', ns_nfe) or
            _xpath_text(xml_elemento, '//ns:dest/ns:CPF', ns_nfe)
        )
        dados['valor'] = _xpath_text(xml_elemento, '//ns:vNF', ns_nfe)
        dados['data_emissao'] = _xpath_text(xml_elemento, '//ns:dhEmi', ns_nfe)
        if dados['data_emissao']:
            dados['data_emissao'] = dados['data_emissao'][:10]
    except Exception:
        pass
    return dados


def _parse_resumo_nfe(xml_elemento) -> dict:
    dados = {}
    try:
        dados['chave'] = _xpath_text(xml_elemento, '//ns:resNFe/ns:chNFe')
        dados['emitente'] = _xpath_text(xml_elemento, '//ns:resNFe/ns:xNome')
        dados['valor'] = _xpath_text(xml_elemento, '//ns:resNFe/ns:vNF')
        dados['data_emissao'] = _xpath_text(xml_elemento, '//ns:resNFe/ns:dhEmi')
        if dados['data_emissao']:
            dados['data_emissao'] = dados['data_emissao'][:10]
    except Exception:
        pass
    return dados


def _parse_evento_nfe(xml_elemento) -> dict:
    dados = {}
    try:
        # chave do próprio evento
        dados['chave'] = _xpath_text(xml_elemento, '//ns:evento/ns:infEvento/ns:Id')
        if dados['chave'].startswith('ID'):
            dados['chave'] = dados['chave'][2:]

        # chave da NF-e referenciada
        dados['chave_ref'] = _xpath_text(xml_elemento, '//ns:evento/ns:infEvento/ns:chNFe')

        dados['tp_evento'] = _xpath_text(xml_elemento, '//ns:evento/ns:infEvento/ns:tpEvento')
        dados['tipo'] = TIPO_EVENTO.get(dados['tp_evento'], f'Evento {dados["tp_evento"]}')

        dados['emitente'] = (
            _xpath_text(xml_elemento, '//ns:evento/ns:infEvento/ns:CNPJ') or
            _xpath_text(xml_elemento, '//ns:evento/ns:infEvento/ns:CPF')
        )
        dados['data_emissao'] = _xpath_text(xml_elemento, '//ns:evento/ns:infEvento/ns:dhEvento')
        if dados['data_emissao']:
            dados['data_emissao'] = dados['data_emissao'][:10]

        # Para CC-e, pega o texto da correção como "valor"
        dados['valor'] = _xpath_text(xml_elemento, '//ns:detEvento/ns:xCorrecao')
    except Exception:
        pass
    return dados


def _processar_lote(resposta, ns=NS) -> list[Documento]:
    docs = []
    items = resposta.xpath('//ns:retDistDFeInt/ns:loteDistDFeInt/ns:docZip', namespaces=ns)
    schemas = resposta.xpath('//ns:retDistDFeInt/ns:loteDistDFeInt/ns:docZip/@schema', namespaces=ns)
    nsus = resposta.xpath('//ns:retDistDFeInt/ns:loteDistDFeInt/ns:docZip/@NSU', namespaces=ns)

    for i, item in enumerate(items):
        schema = schemas[i] if i < len(schemas) else ''
        nsu = nsus[i] if i < len(nsus) else ''
        tipo = TIPO_SCHEMA.get(schema, schema)

        doc = Documento(nsu=nsu, tipo=tipo, schema=schema)

        try:
            zip_b64 = item.text
            xml_elem = DescompactaGzip.descompacta(zip_b64)
            doc.xml_raw = etree.tostring(xml_elem, encoding='unicode')

            if schema == 'procNFe_v4.00.xsd':
                dados = _parse_nfe_completa(xml_elem)
            elif schema == 'resNFe_v1.01.xsd':
                dados = _parse_resumo_nfe(xml_elem)
            elif schema == 'procEventoNFe_v1.00.xsd':
                dados = _parse_evento_nfe(xml_elem)
                doc.tipo = dados.get('tipo', 'Evento NF-e')
                doc.tipo_evento = dados.get('tp_evento', '')
                doc.chave_ref = dados.get('chave_ref', '')
            else:
                dados = {}

            doc.chave = dados.get('chave', '')
            doc.emitente = dados.get('emitente', '')
            doc.destinatario = dados.get('destinatario', '')
            doc.valor = dados.get('valor', '')
            doc.data_emissao = dados.get('data_emissao', '')
        except Exception as e:
            doc.status = f'Erro ao descompactar: {e}'

        docs.append(doc)

    return docs


class ConsultaSefaz:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def parar(self):
        self._stop_event.set()

    def esta_rodando(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def consultar_async(
        self,
        uf: str,
        certificado: str,
        senha: str,
        cnpj: str,
        nsu_inicial: int,
        homologacao: bool,
        pasta_saida: str,
        on_log: Callable[[str], None],
        on_documento: Callable[[Documento], None],
        on_finalizado: Callable[[str], None],
    ):
        self._stop_event.clear()

        def _run():
            try:
                _executar_consulta(
                    uf, certificado, senha, cnpj, nsu_inicial, homologacao,
                    pasta_saida, on_log, on_documento, on_finalizado,
                    self._stop_event,
                )
            except Exception as e:
                on_log(f'[ERRO] {e}')
                on_finalizado('erro')

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()


def _executar_consulta(
    uf, certificado, senha, cnpj, nsu_inicial, homologacao,
    pasta_saida, on_log, on_documento, on_finalizado, stop_event,
):
    if not PYNFE_AVAILABLE:
        raise ImportError('pynfe não está instalado. Execute: pip install pynfe')

    import os
    os.makedirs(pasta_saida, exist_ok=True)

    con = ComunicacaoSefaz(uf, certificado, senha, homologacao)
    nsu = nsu_inicial
    ns = NS

    on_log(f'Iniciando consulta | CNPJ: {cnpj} | NSU inicial: {nsu} | UF: {uf}')
    on_log(f'Ambiente: {"Homologação" if homologacao else "Produção"}')

    while not stop_event.is_set():
        on_log(f'Consultando a partir do NSU: {str(nsu).zfill(15)}')

        try:
            xml_resp = con.consulta_distribuicao(cnpj=cnpj, nsu=nsu)
        except Exception as e:
            on_log(f'[ERRO na comunicação] {e}')
            on_finalizado('erro')
            return

        resposta = etree.fromstring(xml_resp.text.encode('utf-8'))

        cstat = _xpath_text(resposta, '//ns:retDistDFeInt/ns:cStat')
        xmotivo = _xpath_text(resposta, '//ns:retDistDFeInt/ns:xMotivo')
        max_nsu = _xpath_text(resposta, '//ns:retDistDFeInt/ns:maxNSU')
        ult_nsu = _xpath_text(resposta, '//ns:retDistDFeInt/ns:ultNSU')

        on_log(f'cStat: {cstat} | {xmotivo} | maxNSU: {max_nsu}')

        if cstat == '138':
            docs = _processar_lote(resposta)
            on_log(f'{len(docs)} documento(s) neste lote')

            for doc in docs:
                if doc.xml_raw and doc.status == 'OK':
                    nome_arquivo = os.path.join(
                        pasta_saida,
                        f'{doc.schema.split("_")[0]}-NSU-{doc.nsu}.xml'
                    )
                    try:
                        with open(nome_arquivo, 'w', encoding='utf-8') as f:
                            f.write(doc.xml_raw)
                        on_log(f'Salvo: {os.path.basename(nome_arquivo)}')
                    except Exception as e:
                        on_log(f'[AVISO] Não foi possível salvar {nome_arquivo}: {e}')
                on_documento(doc)

            nsu = int(ult_nsu) if ult_nsu else nsu + 1

        elif cstat == '137':
            on_log('Não há mais documentos para pesquisar.')
            on_finalizado('ok')
            return

        else:
            on_log(f'Resposta inesperada do servidor. Encerrando.')
            on_finalizado('erro')
            return

    on_log('Consulta interrompida pelo usuário.')
    on_finalizado('parado')
