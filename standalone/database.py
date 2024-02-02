# import sqlite3
from typing import Sequence, List, Dict, TypedDict
import aiosqlite
import logging
import shared.constants as constants


class MeetingRecord(TypedDict):
    uuid: str
    meeting_title: str
    email_from: str
    email: str
    recurr: bool
    end_date: str
    groups: List[str]
    ics_file_data: str


class TLDatabase:
    _instance = None
    db_path = None

    def __new__(cls, db_path=constants.DB_PATH):
        if cls._instance is None:
            cls._instance = super(TLDatabase, cls).__new__(cls)
            cls.db_path = db_path
        return cls._instance

    async def initialize(self):
        self.conn = await aiosqlite.connect(self.db_path)
        await self._create_tables()

    async def _create_tables(self):
        # cursor = self.conn.cursor()
        await self.conn.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            uuid TEXT PRIMARY KEY,
            meeting_title TEXT,
            email_from TEXT,
            email TEXT,
            recurr BOOLEAN,
            end_date TEXT,
            groups TEXT,
            ics_file_data TEXT,
            created_at TIMESTAMP DEFAULT NULL,
            updated_at TIMESTAMP DEFAULT NULL
        )
        ''')

        # Track each group that was a receipient of the email
        await self.conn.execute('''
        CREATE TABLE IF NOT EXISTS meeting_groups (
            uuid TEXT,
            group_name TEXT,
            created_at TIMESTAMP DEFAULT NULL,
            updated_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (uuid) REFERENCES meetings (uuid) ON DELETE CASCADE,
            PRIMARY KEY (uuid, group_name)
        )
        ''')

        # tracks each user that has received the invite
        await self.conn.execute('''
        CREATE TABLE IF NOT EXISTS meeting_invites (
            uuid TEXT,
            email_address TEXT,
            created_at TIMESTAMP DEFAULT NULL,
            updated_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (uuid) REFERENCES meetings (uuid) ON DELETE CASCADE,
            PRIMARY KEY (uuid, email_address)
        )
        ''')


        # update tables to latest version
        for table in ['meetings', 'meeting_groups', 'meeting_invites']:
            await self.conn.execute(f'''
CREATE TRIGGER IF NOT EXISTS insert_timestamp_trigger_{table}
AFTER INSERT 
ON {table}
FOR EACH ROW
WHEN NEW.created_at IS NULL
BEGIN
    UPDATE {table} SET created_at = CURRENT_TIMESTAMP 
    WHERE rowid = NEW.rowid;
END;
''')
            await self.conn.execute(f'''
CREATE TRIGGER IF NOT EXISTS update_timestamp_trigger_{table}
AFTER UPDATE 
ON {table}
FOR EACH ROW
BEGIN
    UPDATE {table} SET updated_at = CURRENT_TIMESTAMP
      WHERE rowid = NEW.rowid;
END;
''')
            try:
                await self.conn.execute(f'''
ALTER TABLE {table} ADD COLUMN created_at TIMESTAMP DEFAULT NULL;
''')
            except Exception as e:
                # column already exists
                pass
            try:
                await self.conn.execute(f'''
ALTER TABLE {table} ADD COLUMN updated_at TIMESTAMP DEFAULT NULL;
''')
            except Exception as e:
                # column already exists
                pass

        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.commit()

    async def meetings_insert_record(self, record):
        # cursor = self.conn.cursor()
        await self.conn.execute('''
INSERT OR REPLACE INTO meetings
(uuid, meeting_title, email_from, email, recurr, end_date, groups, ics_file_data)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (record['uuid'], record['meeting_title'], record['email_from'],
              record['email'], record['recurr'], record['end_date'],
              ','.join(record['groups']), record['ics_file_data']))
        await self.conn.commit()

    async def meetings_delete_record(self, uuid):
        await self.conn.execute('DELETE FROM meetings WHERE uuid = ?', (uuid,))
        await self.conn.commit()

    async def meetings_invites_delete(self, uuid):
        await self.conn.execute('DELETE FROM meeting_invites WHERE uuid = ?', (uuid,))
        await self.conn.commit()

    async def meetings_invites_set(self, uuid, email_addresses: Sequence[str]):
        for e in email_addresses:
            await self.conn.execute('''
                INSERT OR REPLACE INTO meeting_invites (uuid, email_address)
                VALUES (?, ?)''', (uuid, e))
            await self.conn.commit()
    """
    async def meetings_invites_get(self, uuid: str) -> List[str]:
        cursor = await self.conn.execute('''
            SELECT email_address
            FROM meeting_invites
            WHERE uuid = ?''', (uuid,))

        records = await cursor.fetchall()

        email_addresses = [record[0] for record in records]

        return email_addresses
    """
    async def meetings_invites_get(self, uuids: List[str]) -> Dict[str, List[str]]:
        placeholders = ','.join('?' for uuid in uuids)
        cursor = await self.conn.execute(f'''
            SELECT uuid, email_address
            FROM meeting_invites
            WHERE uuid IN ({placeholders})''', uuids)
        records = await cursor.fetchall()
        # Organize the email addresses by UUID
        email_addresses_by_uuid: Dict[str, List[str]] = {uuid: [] for uuid in uuids}
        for record in records:
            uuid, email_address = record
            email_addresses_by_uuid[uuid].append(email_address)

        return email_addresses_by_uuid

    async def meetings_retrieve_all_records(self) -> List[MeetingRecord]:
        cursor = await self.conn.execute('SELECT * FROM meetings')
        records = await cursor.fetchall()
        return [
            {'uuid': r[0], 'meeting_title': r[1], 'email_from': r[2],
                'email': r[3], 'recurr': r[4], 'end_date': r[5],
                'groups': r[6].split(','), 'ics_file_data': r[7]}
            for r in records]
    
    async def meetings_retrieve_record(self, uuid) -> List[MeetingRecord]:
        cursor = await self.conn.execute('SELECT * FROM meetings WHERE uuid = ?', (uuid,))
        records = await cursor.fetchall()
        return [
            {'uuid': r[0], 'meeting_title': r[1], 'email_from': r[2],
                'email': r[3], 'recurr': r[4], 'end_date': r[5],
                'groups': r[6].split(','), 'ics_file_data': r[7]}
            for r in records]

    async def close(self):
        if not self.conn:
            return
        await self.conn.close()
        self.conn = None
        logging.info('Database connection closed')
