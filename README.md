# WBS-GEN

WBS-GEN は、WBS とガントチャートを一枚の静的HTMLにまとめるローカルCLIです。アカウントやサーバーは不要です。

![標準ビュー](docs/readme/screenshot-standard.png)

## コンセプト

WBS-GENは、WBSとガントチャートの管理を「ファイル1枚」に閉じ込めるローカルCLIです。正本はJSONまたは生成済みHTMLのどちらかを選べ、どちらもテキストベースなのでgitで差分管理できます。サーバーもアカウントも不要で、CLIコマンドとエディタでの手編集を自由に組み合わせて使えます。

## 動作環境

- Python 3.12 以上（OS不問。Windowsでは`python3`ではなく`python`コマンドになる場合があります）
- モダンブラウザ（生成したHTMLの閲覧に使用します）
- インターネット接続は不要です（祝日の自動取得コマンドを使う場合を除く）

## できること

- WBS表とガントチャートを1枚の静的HTMLに集約（担当者・計画/実績期間・進捗・Issueリンク・コメントを列表示）
- イナズマ線で進捗の遅れを可視化、警告タスクは自動ハイライト
- 分析タブで差分・遅れ営業日・必要ペースを確認
- マイルストーン表示、キーワード検索（フィルタ／ハイライト）
- 休日データの取り込み（JSON直接指定・外部JSONファイル、または内閣府CSVの自動取得。自動取得のみインターネット接続が必要）
- 表示列・表示レイヤーのカスタマイズ、URLクエリでの一時共有、JSON/XLSXエクスポート

詳細は[配布用マニュアル](https://github.com/motahead/wbsgen-public/releases/latest/download/wbsgen-manual.html)を参照してください。

![分析タブ](docs/readme/screenshot-analysis.png)

## ダウンロード

- 実行ファイル: [wbsgen.pyz](https://github.com/motahead/wbsgen-public/releases/latest/download/wbsgen.pyz)
- サンプル: [wbsgen-sample.json](https://github.com/motahead/wbsgen-public/releases/latest/download/wbsgen-sample.json)

**詳しい使い方は[配布用マニュアル](https://github.com/motahead/wbsgen-public/releases/latest/download/wbsgen-manual.html)を参照してください。**

## クイックスタート

1. wbsgen.pyz をダウンロードする（上記参照）
2. プロジェクトJSONを作る
   ```sh
   python3 wbsgen.pyz init project.json --name "個人開発"
   ```
3. HTMLを生成して開く
   ```sh
   python3 wbsgen.pyz generate project.json -o project.html
   ```
   `project.html` をブラウザで開くと、WBS表とガントチャートが表示されます。

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

JSONとHTMLのどちらも `validate` と `export xlsx` に渡せます。

## 表示設定

`display.standard.columns` では標準ビューの列表示・初期幅・順序を、`display.analysis.columns.order` では分析ビューの列順を指定します。`display.layers.visible` はガントの表示レイヤーです。`order` は部分指定でき、未指定の列は既定順で末尾に追加されます。HTML上での並べ替えは一時的な表示操作で、JSONやXLSXには書き戻しません。

## テスト

ソースから動作を検証したい場合:

```sh
git clone https://github.com/motahead/wbsgen-public.git
cd wbsgen-public

mise run visual-install  # 初回のみ: visual profile用のChromiumを準備
mise run verify-code
mise run verify-distribution
mise run verify-visual
mise run verify-manual
mise run verify-pr       # まとめて実行する場合
```

各profileの目的は[docs/quality-definition.md](docs/quality-definition.md)を参照してください。

## 免責事項

個人開発のツールです。動作の保証や継続的なサポートは行いません。利用は自己責任でお願いします。

## ライセンス

[MIT License](LICENSE) — フォーク・改変・再配布は自由です。
