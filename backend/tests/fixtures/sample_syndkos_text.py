"""
Sample text fixtures representing Syndkos condo bills (Villa Salomy reference bill).
No emojis used.
"""

VILLA_SALOMY_TEXT_PAGE1 = """CONDOMINIO EDIFICIO VILLA SALOMY
CNPJ: 08.123.456/0001-89
DEMONSTRATIVO DE RATEIO DE 01/09/2026 ATÉ 30/09/2026
VENCIMENTO: 10/10/2026
UNIDADE: 802 - APARTAMENTO
FRAÇÃO IDEAL: 0,04166

DESCRIÇÃO DAS DESPESAS                           TOTAL CONDOMÍNIO    VALOR UNIDADE

DESPESAS ORDINÁRIAS
Manutenção e Conservação de Elevadores                   1.500,00           150,00
Energia Elétrica Áreas Comuns                            1.205,00           120,50
Serviços de Limpeza e Portaria                           2.107,70           210,77
Honorários de Administração                              1.150,00           115,00
SUBTOTAL ORDINÁRIAS                                                         596,27

DESPESAS EXTRAORDINÁRIAS
Seguro Obrigatório Predial Parc 2/6                        442,56            18,44
Tarifa Bancária                                             54,96             2,29
Laudo Bombeiro Parc 2/3                                    263,04            10,96
Rateio Manutenção Fachada Parc 6/10                      4.998,96           208,29
Rateio fiscalização obra da fachada                      1.317,36            54,89
SUBTOTAL EXTRAORDINÁRIAS                                                    294,87

LEITURAS
GÁS                                                         62,21             62,21
ÁGUA                                                       141,33            141,33
SUBTOTAL LEITURAS                                                           203,54

FUNDOS
Fundo de Reserva 10,00%                                    596,30             59,63
SUBTOTAL FUNDOS                                                              59,63

RESUMO DO RATEIO
Total Ordinárias: 596,27
Total Extraordinárias: 294,87
Total Leituras: 203,54
Total Fundos: 59,63
VALOR TOTAL: 1.154,31

13691.10802 00102.557006 00000.514034 2 15950000115431
"""

VILLA_SALOMY_OCR_TEXT = """CONDOMINIO EDIFICIO VILLA SALOMY
DEMONSTRATIVO DE RATEIO DE 01/09/2026 ATE 30/09/2026
Vencimento: 10/10/2026
Unidade: 802

DESPESAS ORDINARIAS
Manutencao e Conservacao de Elevadores 150,00
Energia Eletrica Areas Comuns 120,50
Servicos de Limpeza e Portaria 210,77
Honorarios de Administracao 115,00
Subtotal Ordinarias: 596,27

DESPESAS EXTRAORDINARIAS
Seguro Obrigatorio Predial Parc 2/6 18,44
Tarifa Bancaria 2,29
Laudo Bombeiro Parc 2/3 10,96
Rateio Manutencao Fachada Parc 6/10 208,29
Rateio fiscalizacao obra da fachada 54,89
Subtotal Extraordinarias: 294,87

LEITURAS
GAS 62,21
AGUA 141,33
Subtotal Leituras: 203,54

FUNDOS
Fundo de Reserva 10,00% 59,63
Subtotal Fundos: 59,63

RESUMO
Total Ordinarias: 596,27
Total Extraordinarias: 294,87
Total Leituras: 203,54
Total Fundos: 59,63
VALOR TOTAL: 1.154,31

Linha Digitavel: 13691.10802 00102.557006 00000.514034 2 15950000115431
"""

VILLA_SALOMY_INVALID_MATH_TEXT = """CONDOMINIO EDIFICIO VILLA SALOMY
DEMONSTRATIVO DE RATEIO DE 01/09/2026 ATÉ 30/09/2026
VENCIMENTO: 10/10/2026

DESPESAS ORDINÁRIAS
Manutenção e Conservação 150,00
SUBTOTAL ORDINÁRIAS 150,00

DESPESAS EXTRAORDINÁRIAS
Laudo Bombeiro 10,96
SUBTOTAL EXTRAORDINÁRIAS 10,96

LEITURAS
ÁGUA 100,00
SUBTOTAL LEITURAS 100,00

FUNDOS
Fundo de Reserva 50,00
SUBTOTAL FUNDOS 50,00

VALOR TOTAL: 9999.99
13691.10802 00102.557006 00000.514034 2 15950000115431
"""
