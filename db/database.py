"""数据库连接与会话管理"""

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from db.entity.base_entity import BaseEntity
from error.errors import BaseError, ConfigError, DatabaseError

load_dotenv()

class Database:
    """数据库连接封装类。持有engine与session工厂"""

    def __init__(
            self,
            url: Optional[str] = None,
            echo: Optional[bool] = None,
            poolSize: Optional[int] = None,
            maxOverflow: Optional[int] = None
        ):
        """
        初始化数据库连接。优先使用传入参数，如果未提供，则从环境变量加载。
        """
        try:
            url = url or os.getenv("DATABASE_URL", "")
            if not url:
                raise ConfigError("数据库连接地址必须被提供或在.env文件中的DATABASE_URL定义。")
            if echo is None:
                echo = os.getenv("ECHO", "false").strip().lower() in ("1", "true", "yes", "on")
            try:
                poolSize = poolSize or int(os.getenv("POOL_SIZE", 10))
                maxOverflow = maxOverflow or int(os.getenv("MAX_OVERFLOW", 20))
            except ValueError:
                raise ConfigError("数据库的poolSize与maxOverflow必须是整数")

            self.engine: Engine = create_engine(
                url,
                echo=echo,
                pool_size=poolSize,
                max_overflow=maxOverflow,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
        except BaseError:
            raise
        except Exception as e:
            raise ConfigError(f"数据库配置出错：{e}")

        self.sessionFactory = sessionmaker(bind=self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """会话上下文管理器。正常退出时提交，异常时回滚，最后关闭会话"""
        session = self.sessionFactory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            raise DatabaseError(f"数据库操作失败：{e}")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_tables(self) -> None:
        """按实体定义建表，已存在的表不会被改动"""
        try:
            BaseEntity.metadata.create_all(self.engine)
        except SQLAlchemyError as e:
            raise DatabaseError(f"建表失败：{e}")

    def dispose(self) -> None:
        """释放连接池"""
        self.engine.dispose()

_database: Optional[Database] = None

def init_database(
        url: Optional[str] = None,
        echo: Optional[bool] = None,
        poolSize: Optional[int] = None,
        maxOverflow: Optional[int] = None
    ) -> Database:
    """初始化全局数据库实例。应在应用入口调用一次"""
    global _database
    if _database is not None:
        _database.dispose()
    _database = Database(url=url, echo=echo, poolSize=poolSize, maxOverflow=maxOverflow)
    return _database

def get_database() -> Database:
    """获取全局数据库实例。未初始化时按环境变量惰性初始化"""
    global _database
    if _database is None:
        _database = Database()
    return _database

@contextmanager
def get_session() -> Generator[Session, None, None]:
    """全局数据库实例的会话上下文管理器"""
    with get_database().session() as session:
        yield session
