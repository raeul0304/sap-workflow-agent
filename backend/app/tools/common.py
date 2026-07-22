# 공통 python Tool

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from datetime import datetime
from typing import Any, List, Dict
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()


def get_current_time() -> dict[str, Any]:
    """현재 한국 시간을 반환"""
    location = "Asia/Seoul"
    now = datetime.now(ZoneInfo(location))
    
    return {
        "datetime": now.isoformat(),
        "date": now.date().isoformat(),
        "time": now.time().isoformat(timespec="seconds"),
        "timezone": location
    }


def get_db_connection():
    try:
        conn = psycopg2.connect(
            host = os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
        print("[Debug] DB 연결 성공")
        return conn
    except Exception as e:
        print(f"[Error] DB 연결 실패: {e}")
        raise e


def read_dataset(tableName: str) -> List[Dict[str, Any]]:
    try:
        conn = get_db_connection()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = sql.SQL("SELECT * FROM {}.{} LIMIT 5").format(
                sql.Identifier('mart'),
                sql.Identifier(tableName)
            )
            print(f"[Debug] 실행할 쿼리: {query.as_string(conn)}")
            cur.execute(query)
            rows = cur.fetchall()

            print(f"[Debug] 조회된 데이터 건수: {len(rows)}건")

            result_list = []
            for idx, row in enumerate(rows):
                row_dict = dict(row)
                print(f"[Debug] Row {idx + 1}: {row_dict}")
                result_list.append(row_dict)
            
            return result_list
    except Exception as e:
        print(f"[Error] 데이터 조회 중 오류 발생 : {e}")
        return []
    finally:
        if conn:
            conn.close()
            print("[Debug] DB 연결 종료")




TOOL_REGISTRY = {
    "get_current_time": get_current_time,
    "read_dataset": read_dataset,
}