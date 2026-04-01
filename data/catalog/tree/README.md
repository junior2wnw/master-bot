# Catalog Tree

Канонический редактируемый источник каталога теперь находится в `data/catalog/tree`.
`data/catalog/catalog_bundle.json` больше не является основным местом ручного редактирования и должен пересобираться из дерева.

Структура:

- `metadata.json`: версия, источники, контекст рыночного обновления.
- `shared_operations.json`: общий справочник операций.
- `estimator_fields.json`: вопросы и поля для сметчика.
- `coefficients.json`: коэффициенты и наценки.
- `<NN>_<profession>/profession.json`: верхний раздел каталога.
- `<NN>_<profession>/groups/<NN>_<group>/group.json`: группа внутри профессии.
- `<NN>_<profession>/groups/<NN>_<group>/subgroups/<NN>_<subgroup>/subgroup.json`: подгруппа.
- `<NN>_<profession>/groups/<NN>_<group>/subgroups/<NN>_<subgroup>/items.json`: редактируемые работы и цены.

Правила редактирования:

- Меняйте цены и названия только в `items.json` нужной подгруппы.
- Для новых услуг сначала проверьте, есть ли подходящие `shared_ops` и `estimator_fields`.
- Если услуга добавляется как отдельный SKU, сохраняйте понятный код, `sort_order` и рыночный источник.
- Для bundle- и replacement-позиций проверяйте `excludes`, чтобы смета не дублировала атомарные работы.
- После правок пересобирайте bundle командой `python -m scripts.catalog_tree build --tree-root data/catalog/tree --output data/catalog/catalog_bundle.json`.

Важно:

- Runtime по умолчанию читает каталог из дерева, если `data/catalog/tree/metadata.json` существует.
- JSON bundle нужен как сборочный артефакт, импортный снимок и резервный fallback.
