from pathlib import Path
import time
from reconcile_core import compare_rows, totals_rows

# A small mirror-act fixture: summaries must be ignored, document numbers can
# differ for payments, and debit/credit sides are reversed between parties.
rows1 = [
    {'Дата':'', 'Документ':'Сальдо начальное', 'Дебет':'', 'Кредит':1000},
    {'Дата':'01.07.26', 'Документ':'Поступление товаров и услуг № УТ-100 от 01.07.2026', 'Дебет':'', 'Кредит':120},
    {'Дата':'01.07.26', 'Документ':'Платежное поручение исходящее № BANK-77 от 01.07.2026', 'Дебет':50, 'Кредит':''},
    {'Дата':'', 'Документ':'Обороты за период', 'Дебет':50, 'Кредит':120},
    {'Дата':'', 'Документ':'Сальдо конечное', 'Дебет':'', 'Кредит':1070},
]
rows2 = [
    {'Дата':'', 'Документ':'Сальдо на 01.07.26', 'Дебет':1000, 'Кредит':''},
    {'Дата':'01.07.26', 'Документ':'Отгрузка 01.07.26 ( №УТ-100)', 'Дебет':120, 'Кредит':''},
    {'Дата':'01.07.26', 'Документ':'Оплата 01.07.26 ( №00012345)', 'Дебет':'', 'Кредит':50},
    {'Дата':'', 'Документ':'Обороты за период', 'Дебет':120, 'Кредит':50},
    {'Дата':'', 'Документ':'Сальдо конечное', 'Дебет':1070, 'Кредит':''},
]
cols = {'date':'Дата','document':'Документ','debit':'Дебет','credit':'Кредит','balance':None,'counterparty':None}
result, p1, p2 = compare_rows(rows1, rows2, cols, cols, 0.01)
differences, only1, only2, matches = result
assert not differences, differences
assert not only1, only1
assert not only2, only2
assert len(matches) == 2, matches
assert abs(p1['accrual'] - 120.0) < 0.001
assert abs(p2['accrual'] - 120.0) < 0.001
assert abs(p1['settlement'] - 50.0) < 0.001
assert abs(p2['settlement'] - 50.0) < 0.001

# Stress the exact-number index. This catches accidental O(N²) regressions in
# the button path without embedding any customer data into the public repo.
large1 = []
large2 = []
for i in range(1, 2501):
    amount = 10.0 + i / 100.0
    large1.append({'Дата':'01.07.26','Документ':f'Поступление № УТ-{i} от 01.07.2026','Дебет':'','Кредит':amount})
    large2.append({'Дата':'01.07.26','Документ':f'Отгрузка 01.07.26 ( №УТ-{i})','Дебет':amount,'Кредит':''})
start = time.perf_counter()
res, _, _ = compare_rows(large1, large2, cols, cols, 0.01)
elapsed = time.perf_counter() - start
assert len(res[3]) == 2500, len(res[3])
assert not res[0] and not res[1] and not res[2]
assert elapsed < 8.0, f'Сверка слишком медленная: {elapsed:.2f} сек.'

source = Path('main.py').read_text(encoding='utf-8')
assert 'MainScreen.run_compare = _stable_run_compare' in source
assert 'Thread(target=' not in source
assert 'faulthandler.enable' not in source
assert '__version__ = "1.12.0"' in source
assert 'self.result_label.markup = False' in source
assert 'self.result_label.height = dp(190)' not in source
assert '[b]Сверка завершена[/b]' not in source
print(f'Runtime smoke test OK: 2500+2500 документов за {elapsed:.2f} сек.')
