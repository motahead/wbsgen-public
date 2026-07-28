# WBS-GEN 品質定義

WBS-GEN は、利用者が編集する JSON、そこから生成する HTML、配布する zipapp が同じ WBS 情報を正しく扱えることを保証する。品質確認は、人間の設計判断と機械的な契約検証を混同しない。

## 保証するもの

- 標準サンプルは警告・エラーなしで `validate`、HTML 生成、JSON 往復、XLSX 出力できる。
- 配布 zipapp は公開 CLI の主要コマンド群を、固定 fixture に対して一連の利用シナリオとして実行できる。更新後は埋め込み JSON と HTML DOM が整合し、`export` と `refresh` で意味的な情報を失わない。
- 表示実装は、合意済み design SSOT である `mockups/visual-reference.html` と構造パリティを保つ。design SSOT は生成物で上書きしない。
- ランダム入力による探索的 QA は、記録した seed で再実行できる。重要な seed は固定 fixture として昇格する。

## Verification profiles

| Profile | 目的 | 主な入口 | 実行タイミング |
| --- | --- | --- | --- |
| `verify-code` | ソース単位の回帰、coverage、pytest 収集 | `mise run verify-code` | 実装後 |
| `verify-distribution` | 固定 fixture で配布 zipapp の公開 CLI を一周 | `mise run verify-distribution` | 最終確認時 |
| `verify-visual` | visual fixture の生成 HTML と design SSOT の構造パリティ | `mise run verify-visual` | 表示変更後 |
| `verify-manual` | MANUAL 図版・内容の整合 | `mise run verify-manual` | 最終確認時 |
| `verify-pr` | 上記4 profile の最終確認用の合成 | `mise run verify-pr` | 最終確認時 |
| `qa-explore` | seed 付きランダム入力での探索的耐性確認 | `mise run qa-explore -- --seed N` | 明示的なQAとして必要なときに実行する。通常の実行タイミングには含めない |

`capture-visual` は screenshot を求められた人間向け観察ツールである。スクリーンショットは設計パリティや通常の品質判定の材料にしない。

## カバレッジ基準

機械的に測定・強制するカバレッジ基準は C0（命令網羅）と C1（分岐網羅）とする。`coverage.py` は分岐計測を有効にし、全体のカバレッジ下限は 80% とする。C2（条件組み合わせ）は機械的な強制対象にはしないが、テスト設計では意識する。

カバレッジ下限を変更する場合は、変更理由を明記する。

## Fixture と成果物

- `examples/sample.json` は利用者向け・Release 添付用の小さな正常系であり、複雑な検証 fixture に転用しない。
- `tests/fixtures/distribution-workflow.json` と `distribution-holidays.json` は固定 CLI 契約専用である。
- `examples/visual-test.json` は visual profile の入力、`mockups/visual-reference.html` は人間が合意する design SSOT である。
- 生成物は `output/` に置く。`output/distribution`、`output/visual`、`output/captures`、`output/qa/<seed>` はそれぞれの runner 専用の作業領域であり、他の runner は変更しない。`dist/` と `output/` は追跡しない。
- `capture-visual` は `output/captures/visual-test.html` と3枚の定型PNGだけを新規作成または上書きする。`output/captures/` 全体は削除しない。

## Fixed distribution contract

`verify-distribution` は、固定 fixture に対して配布 zipapp の公開 CLI を一連の利用シナリオとして実行する。

| CLI系統 | 実行する代表操作 |
| --- | --- |
| 起点 | `--version`、`init`、`template` |
| 生成・検証 | JSON／HTMLの `validate`、`generate`、`generate --holidays`、`refresh`、`version` |
| `project` | `show` → `update` → `show` |
| `task` | `show` → `add` → `update` → `move` → `remove` |
| `milestone` | `show` → `add` → `update` → `remove` |
| `holiday` | `show` → `add` → `update` → `merge` → `remove` |
| `display` | `show` → `standard` / `analysis` / `layers` の `update` → `show` |
| export | HTMLから `export json`、JSONとHTMLの両方から `export xlsx` |

各操作では、必要に応じて次を確認する。

- 更新直後のデータを `show` または `export json` で確認する。
- 更新後のHTMLについて、埋め込みJSONとDOMの状態が整合することを確認する。
- シナリオ終盤で `export json` → JSON編集 → `generate` → `export json` を実行し、意味的な情報を失わないことを確認する。
- JSON入力とHTML入力の双方から `export xlsx` を実行し、Office Open XMLのZIP整合、ワークブック、プロジェクト名、WBS行を確認する。

これは固定・再現可能な回帰検証である。通常利用に近いランダムな組合せを網羅する目的は `qa-explore` に分離する。

## Visual design contract

表示変更では、実装前に design SSOT を手で更新し、利用者の合意を得る。実装後は `verify-visual` を実行する。

差分が出た場合は、実装が設計からずれたのか、設計変更を新たに合意すべきなのかを判断する。生成 HTML を mockup にコピーして差分を消してはならない。必要なら `capture-visual` を使って人間が観察するが、これは補助資料である。
