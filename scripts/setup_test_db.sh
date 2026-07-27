#!/usr/bin/env bash
# 把本 repo 的 schema 套用到 garyu 專用的本機 Supabase（測試用），並產生 .env.test.local。
#
# 為什麼需要這支腳本
# ------------------
# 本 repo 的 schema 散在兩個目錄、編號還互相碰撞（db/supabase_migrations/002 與
# supabase_migrations/002 是不同的東西），而且正式環境是「手動貼進 Supabase dashboard
# SQL Editor」套用的——所以 repo 裡從來沒有一個地方寫著「正確的套用順序是什麼」。
# 這支腳本就是那個地方。刻意不把 SQL 複製進 supabase/migrations/：複製會漂移，
# 之後有人新增 migration 卻忘了同步，本機測試庫就會悄悄少一個欄位。
#
# 用法： bash scripts/setup_test_db.sh
# 前置： npx supabase start（本 repo 的 stack，API 54331 / DB 54332）
set -euo pipefail

CONTAINER="supabase_db_garyu-news-scraper"
DB="postgres"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "✗ 找不到容器 $CONTAINER" >&2
    echo "  請先在本 repo 執行： npx supabase start" >&2
    exit 1
fi

# 套用順序：基礎 schema → db/ 的早期 migration → 交通管線的 migration。
# 這個順序是實測出來的（2026-07-27），不是憑檔名猜的。
FILES=(
    db/supabase_schema.sql
    db/supabase_migrations/001_add_content_fingerprint.sql
    db/supabase_migrations/002_add_content_type.sql
    # db/supabase_migrations/003_normalize_published_timestamps.sql
    #   ↑ 刻意跳過。它是「資料」正規化不是 schema——把舊的 TEXT 空字串 published
    #     轉成 NULL。在全新的庫上 published 已經是 TIMESTAMPTZ，`published = ''`
    #     會直接噴 invalid input syntax。空庫沒有資料要正規化，跳過無損。
    supabase_migrations/002_traffic_pipeline.sql
    supabase_migrations/003_embedding_dedup.sql
    supabase_migrations/004_hot_topic_novelty.sql
    supabase_migrations/005_add_image_url.sql
)

for f in "${FILES[@]}"; do
    if docker exec -i "$CONTAINER" psql -U postgres -d "$DB" -v ON_ERROR_STOP=1 -q < "$f" >/dev/null 2>&1; then
        echo "✓ $f"
    else
        echo "✗ $f" >&2
        docker exec -i "$CONTAINER" psql -U postgres -d "$DB" -v ON_ERROR_STOP=1 < "$f" 2>&1 | tail -5 >&2
        exit 1
    fi
done

# 授權給 service_role。表是用 postgres 這個角色透過 psql 直接建的，不會自動帶上
# Supabase 平常給的 grant，所以 PostgREST 會回 42501 permission denied。
# 只授權 service_role（測試用的那把金鑰），不給 anon／authenticated——
# 這些表沒有 RLS，給 anon 等於本機任何人拿 anon key 就能讀寫。
docker exec -i "$CONTAINER" psql -U postgres -d "$DB" -q <<'SQL' >/dev/null
GRANT USAGE ON SCHEMA public TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
SQL

# PostgREST 需要重新載入 schema cache，否則剛建好的表會回 404
docker exec "$CONTAINER" psql -U postgres -d "$DB" -q -c "NOTIFY pgrst, 'reload schema';" >/dev/null

echo
echo "已建立的表："
docker exec "$CONTAINER" psql -U postgres -d "$DB" -t -c \
    "select '  '||table_name||' ('||count(*)||' 欄)' from information_schema.columns
     where table_schema='public' group by table_name order by 1;"

# 產生測試用連線設定。金鑰只寫進 gitignored 的檔案，不印到終端機。
ENV_FILE=".env.test.local"
API_URL=$(npx --yes supabase@latest status -o env 2>/dev/null | grep '^API_URL=' | cut -d= -f2- | tr -d '"')
SERVICE_KEY=$(npx --yes supabase@latest status -o env 2>/dev/null | grep '^SERVICE_ROLE_KEY=' | cut -d= -f2- | tr -d '"')

if [ -z "$API_URL" ] || [ -z "$SERVICE_KEY" ]; then
    echo "✗ 無法從 supabase status 取得連線資訊" >&2
    exit 1
fi

{
    echo "# 由 scripts/setup_test_db.sh 產生。gitignored，不要提交。"
    echo "# 整合測試專用——tests/integration/conftest.py 會讀這個檔並強制指向這裡。"
    echo "SUPABASE_TEST_URL=$API_URL"
    echo "SUPABASE_TEST_SERVICE_ROLE_KEY=$SERVICE_KEY"
} > "$ENV_FILE"

echo
echo "✓ 已寫入 $ENV_FILE（URL=$API_URL，金鑰未顯示）"
echo "  現在可以跑： python -m pytest tests/integration -q"
