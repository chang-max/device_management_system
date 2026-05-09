"""
用户管理模块 - 数据库操作层
用于管理sys_user表的用户信息
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple


class UserManagerDB:
    """用户管理数据库操作类"""

    def __init__(self, db_pool):
        """
        初始化
        :param db_pool: 数据库连接池
        """
        self.db_pool = db_pool
        self.table_name = "sys_user"

    def get_all_users(self) -> List[Dict]:
        """
        获取所有用户信息
        :return: 用户列表
        """
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    sql = f"""
                        SELECT `用户名`, `密码`, `有效期`, `MAC绑定`, `区域信息`
                        FROM `{self.table_name}`
                        ORDER BY `用户名`
                    """
                    cursor.execute(sql)
                    rows = cursor.fetchall()

                    users = []
                    for row in rows:
                        users.append({
                            'username': row['用户名'],
                            'password': row['密码'],
                            'expiry_date': row['有效期'],
                            'mac_bind': row['MAC绑定'],
                            'area_info': row.get('区域信息', '{}')  # 区域信息字段
                        })
                    return users
        except Exception as e:
            print(f"获取用户列表失败: {e}")
            return []

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """
        根据用户名获取用户信息
        :param username: 用户名
        :return: 用户信息字典或None
        """
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    sql = f"""
                        SELECT `用户名`, `密码`, `有效期`, `MAC绑定`
                        FROM `{self.table_name}`
                        WHERE `用户名` = %s
                    """
                    cursor.execute(sql, (username,))
                    row = cursor.fetchone()

                    if row:
                        return {
                            'username': row['用户名'],
                            'password': row['密码'],
                            'expiry_date': row['有效期'],
                            'mac_bind': row['MAC绑定']
                        }
                    return None
        except Exception as e:
            print(f"获取用户信息失败: {e}")
            return None

    def add_user(self, username: str, password: str,
                 expiry_date: Optional[datetime] = None,
                 mac_bind: str = "FF:FF:FF:FF:FF:FF",
                 area_info: str = "{}") -> Tuple[bool, str]:
        """
        新增用户
        :param username: 用户名
        :param password: 密码
        :param expiry_date: 有效期，默认为当前时间后3个月
        :param mac_bind: MAC绑定地址，默认为FF:FF:FF:FF:FF:FF
        :param area_info: 区域信息，默认为空JSON对象"{}"
        :return: (是否成功, 消息)
        """
        # 默认有效期为3个月后
        if expiry_date is None:
            expiry_date = datetime.now() + timedelta(days=90)

        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    # 检查用户名是否已存在
                    check_sql = f"SELECT COUNT(*) as count FROM `{self.table_name}` WHERE `用户名` = %s"
                    cursor.execute(check_sql, (username,))
                    result = cursor.fetchone()

                    if result and result['count'] > 0:
                        return False, "用户名已存在"

                    # 插入新用户
                    insert_sql = f"""
                        INSERT INTO `{self.table_name}` (`用户名`, `密码`, `有效期`, `MAC绑定`, `区域信息`)
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_sql, (username, password, expiry_date, mac_bind, area_info))
                    conn.commit()
                    return True, "用户添加成功"
        except Exception as e:
            return False, f"添加用户失败: {e}"

    def update_user(self, username: str, password: Optional[str] = None,
                    expiry_date: Optional[datetime] = None,
                    mac_bind: Optional[str] = None) -> Tuple[bool, str]:
        """
        修改用户信息
        :param username: 用户名
        :param password: 密码（可选）
        :param expiry_date: 有效期（可选）
        :param mac_bind: MAC绑定地址（可选）
        :return: (是否成功, 消息)
        """
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    # 检查用户是否存在
                    check_sql = f"SELECT COUNT(*) as count FROM `{self.table_name}` WHERE `用户名` = %s"
                    cursor.execute(check_sql, (username,))
                    result = cursor.fetchone()

                    if not result or result['count'] == 0:
                        return False, "用户不存在"

                    # 构建更新字段
                    update_fields = []
                    params = []

                    if password is not None:
                        update_fields.append("`密码` = %s")
                        params.append(password)

                    if expiry_date is not None:
                        update_fields.append("`有效期` = %s")
                        params.append(expiry_date)

                    if mac_bind is not None:
                        update_fields.append("`MAC绑定` = %s")
                        params.append(mac_bind)

                    if not update_fields:
                        return False, "没有要更新的字段"

                    # 执行更新
                    update_sql = f"""
                        UPDATE `{self.table_name}`
                        SET {', '.join(update_fields)}
                        WHERE `用户名` = %s
                    """
                    params.append(username)
                    cursor.execute(update_sql, tuple(params))
                    conn.commit()
                    return True, "用户信息更新成功"
        except Exception as e:
            return False, f"更新用户失败: {e}"

    def delete_user(self, username: str) -> Tuple[bool, str]:
        """
        删除用户
        :param username: 用户名
        :return: (是否成功, 消息)
        """
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    # 检查用户是否存在
                    check_sql = f"SELECT COUNT(*) as count FROM `{self.table_name}` WHERE `用户名` = %s"
                    cursor.execute(check_sql, (username,))
                    result = cursor.fetchone()

                    if not result or result['count'] == 0:
                        return False, "用户不存在"

                    # 删除用户
                    delete_sql = f"DELETE FROM `{self.table_name}` WHERE `用户名` = %s"
                    cursor.execute(delete_sql, (username,))
                    conn.commit()
                    return True, "用户删除成功"
        except Exception as e:
            return False, f"删除用户失败: {e}"

    def unbind_mac(self, username: str) -> Tuple[bool, str]:
        """
        MAC解绑 - 将MAC地址重置为FF:FF:FF:FF:FF:FF
        :param username: 用户名
        :return: (是否成功, 消息)
        """
        return self.update_user(username, mac_bind="FF:FF:FF:FF:FF:FF")

    def check_user_exists(self, username: str) -> bool:
        """
        检查用户是否存在
        :param username: 用户名
        :return: 是否存在
        """
        try:
            with self.db_pool.connection() as conn:
                with conn.cursor() as cursor:
                    sql = f"SELECT COUNT(*) as count FROM `{self.table_name}` WHERE `用户名` = %s"
                    cursor.execute(sql, (username,))
                    result = cursor.fetchone()
                    return result and result['count'] > 0
        except Exception as e:
            print(f"检查用户存在性失败: {e}")
            return False
