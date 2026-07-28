# WBS-GEN

WBS-GEN は、WBS とガントチャートを一枚の静的HTMLにまとめるローカルCLIです。アカウントやサーバーは不要です。

実行ファイルは[最新の wbsgen.pyz](https://github.com/motahead/wbsgen-public/releases/latest/download/wbsgen.pyz)から取得できます。動作確認用のサンプルは[wbsgen-sample.json](https://github.com/motahead/wbsgen-public/releases/latest/download/wbsgen-sample.json)から取得できます。

## JSON運用: 一括編集・Git管理

JSONをエディターやスクリプトで管理し、HTML正本を作成します。

```sh
python3 wbsgen.pyz init project.json --name "個人開発"
python3 wbsgen.pyz generate project.json -o project.html
```

`generate` は入力JSONを変更せず、HTMLに埋め込むコピーへ生成元バージョンを記録します。既存の出力は拒否されるため、置換には `--overwrite` を指定します。

## HTML運用: 日々の参照・更新

生成済みHTMLをそのまま開き、日々の更新も同じファイルへ行えます。

```sh
python3 wbsgen.pyz task update project.html --id 1.2 --progress 50
python3 wbsgen.pyz refresh project.html
python3 wbsgen.pyz export json project.html -o backup.json
```

更新コマンドは、埋め込みJSONを検証してHTML全体を再生成し、入力HTMLをアトミックに置き換えます。`--dry-run` は保存せずJSON差分だけを表示します。ブラウザー画面からの編集、クラウド同期の競合解決、自動同期は対象外です。

JSONとHTMLのどちらも `validate` と `export xlsx` に渡せます。詳細なコマンド一覧、入力形式、移行手順は[配布用マニュアル](https://github.com/motahead/wbsgen-public/releases/latest/download/wbsgen-manual.html)を参照してください。

## 表示設定

`display.standard.columns` では標準ビューの列表示・初期幅・順序を、`display.analysis.columns.order` では分析ビューの列順を指定します。`display.layers.visible` はガントの表示レイヤーです。`order` は部分指定でき、未指定の列は既定順で末尾に追加されます。HTML上での並べ替えは一時的な表示操作で、JSONやXLSXには書き戻しません。

## テスト

```sh
# 初回のみ: visual profile用のChromiumを準備
mise run visual-install

mise run verify-code
mise run verify-distribution
mise run verify-visual
mise run verify-manual

# PR前の総合確認
mise run verify-pr
```
