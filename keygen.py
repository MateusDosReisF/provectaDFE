#!/usr/bin/env python3
"""
Gerador de chaves de ativação — Provecta NF-e

Uso:
    python keygen.py                          # interativo
    python keygen.py --dias 365 --qtd 1       # 1 chave, 365 dias
    python keygen.py --dias 180 --qtd 5       # 5 chaves, 180 dias
    python keygen.py --dias 30 --ilimitado    # sem limite de ativações
    python keygen.py --inspecionar XXXXX-...  # inspeciona uma chave existente
    python keygen.py --verificar XXXXX-...    # valida uma chave existente
"""

import argparse
import sys
from datetime import datetime

from licenca import gerar_chave, inspecionar_chave, validar_chave


def _cabecalho():
    print()
    print('╔══════════════════════════════════════════╗')
    print('║     Provecta NF-e — Gerador de Chaves    ║')
    print('╚══════════════════════════════════════════╝')
    print()


def _gerar_lote(dias: int, qtd: int, max_ativ: int):
    from datetime import timedelta
    exp_dt = datetime.now() + timedelta(days=dias)

    print(f'Gerando {qtd} chave(s) | Validade: {dias} dias ({exp_dt.strftime("%d/%m/%Y")}) | '
          f'Ativações: {"ilimitadas" if max_ativ == 0 else max_ativ}')
    print('─' * 56)

    chaves = []
    for i in range(qtd):
        chave = gerar_chave(dias_validade=dias, max_ativacoes=max_ativ)
        chaves.append(chave)
        print(f'  [{i+1:03d}]  {chave}')

    print('─' * 56)
    print(f'Total: {len(chaves)} chave(s) gerada(s)\n')

    # Salvar em arquivo
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    nome = f'chaves_{ts}.txt'
    with open(nome, 'w', encoding='utf-8') as f:
        f.write(f'Provecta NF-e — Chaves geradas em {datetime.now().strftime("%d/%m/%Y %H:%M")}\n')
        f.write(f'Validade: {dias} dias (até {exp_dt.strftime("%d/%m/%Y")})\n')
        f.write(f'Ativações por chave: {"ilimitadas" if max_ativ == 0 else max_ativ}\n')
        f.write('─' * 56 + '\n')
        for c in chaves:
            f.write(c + '\n')

    print(f'Chaves salvas em: {nome}')
    return chaves


def _inspecionar(chave: str):
    info = inspecionar_chave(chave)
    print(f'\nChave: {chave}')
    print('─' * 56)
    print(f'  Assinatura OK : {"Sim" if info["assinatura_ok"] else "NÃO (inválida!)"}')
    print(f'  Expiração     : {info["expiracao"]}')
    print(f'  Expirada      : {"Sim" if info["expirada"] else "Não"}')
    print(f'  Max ativações : {info["max_ativacoes"]}')
    print(f'  Status geral  : {"VÁLIDA" if info["valida"] and not info["expirada"] else "INVÁLIDA/EXPIRADA"}')
    print()


def _verificar(chave: str):
    ok, msg = validar_chave(chave)
    status = 'VÁLIDA' if ok else 'INVÁLIDA'
    print(f'\n[{status}] {msg}\n')


def _modo_interativo():
    _cabecalho()
    print('Opções:')
    print('  1) Gerar chaves')
    print('  2) Inspecionar chave existente')
    print('  3) Sair')
    print()

    opcao = input('Escolha: ').strip()

    if opcao == '1':
        try:
            dias = int(input('Dias de validade [365]: ').strip() or '365')
            qtd = int(input('Quantidade de chaves [1]: ').strip() or '1')
            ilim = input('Ativações ilimitadas? (s/N): ').strip().lower()
            if ilim == 's':
                max_ativ = 0
            else:
                max_ativ = int(input('Máx. ativações por chave [1]: ').strip() or '1')
        except ValueError:
            print('Valor inválido.')
            sys.exit(1)
        _gerar_lote(dias, qtd, max_ativ)

    elif opcao == '2':
        chave = input('Cole a chave: ').strip()
        _inspecionar(chave)

    elif opcao == '3':
        sys.exit(0)
    else:
        print('Opção inválida.')


def main():
    parser = argparse.ArgumentParser(
        description='Gerador de chaves de ativação Provecta NF-e',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--dias', type=int, default=365, help='Dias de validade (default: 365)')
    parser.add_argument('--qtd', type=int, default=1, help='Quantidade de chaves a gerar (default: 1)')
    parser.add_argument('--ativacoes', type=int, default=1, help='Máx. ativações por chave (default: 1)')
    parser.add_argument('--ilimitado', action='store_true', help='Ativações ilimitadas')
    parser.add_argument('--inspecionar', metavar='CHAVE', help='Inspeciona uma chave existente')
    parser.add_argument('--verificar', metavar='CHAVE', help='Verifica se uma chave é válida')
    parser.add_argument('--interativo', action='store_true', help='Modo interativo (padrão se sem args)')

    args = parser.parse_args()

    _cabecalho()

    if args.inspecionar:
        _inspecionar(args.inspecionar)
    elif args.verificar:
        _verificar(args.verificar)
    elif len(sys.argv) == 1 or args.interativo:
        _modo_interativo()
    else:
        max_ativ = 0 if args.ilimitado else args.ativacoes
        _gerar_lote(args.dias, args.qtd, max_ativ)


if __name__ == '__main__':
    main()
