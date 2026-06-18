from app.core.database import get_supabase

class BaseRepository:
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.db = get_supabase()

    def get_by_id(self, id: str, select: str = "*"):
        return self.db.table(self.table_name).select(select).eq("id", id).single().execute()

    def list_all(self, filters: dict = None, select: str = "*"):
        query = self.db.table(self.table_name).select(select)
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        return query.execute()

    def create(self, data: dict):
        return self.db.table(self.table_name).insert(data).execute()

    def update(self, id: str, data: dict):
        return self.db.table(self.table_name).update(data).eq("id", id).execute()

    def delete(self, id: str):
        return self.db.table(self.table_name).delete().eq("id", id).execute()
