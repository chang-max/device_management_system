-- ============================================================
-- 设备管理系统数据库优化方案
-- 适用场景: 服务器5000-10000设备, 客户端1000-2000设备
-- 版本: v1.0
-- 日期: 2026-05-09
-- ============================================================

-- ============================================================
-- 一、现有数据库结构分析
-- ============================================================

/*
现有表结构:
1. device_info - 设备信息主表
2. sys_user - 用户信息表
3. config - 配置表
4. {device_id} - 设备原始数据表(动态创建,每个设备一个)
5. {device_id}_parsed - 设备解析数据表(动态创建)
6. {device_id}_power - 设备功率记录表(动态创建)
7. summary_power - 功率汇总表
8. summary_power_by_area - 区域功率汇总表
9. summary_daily_online - 每日在线率汇总表
10. summary_daily_online_by_area - 区域每日在线率汇总表
11. summary_daily_electricity - 每日能耗汇总表
12. summary_daily_electricity_by_area - 区域每日能耗汇总表
13. device_area_mapping - 设备区域映射视图

问题:
- 设备数据表数量过多(5000-10000个表),影响MySQL性能
- 缺少分区,大数据量查询慢
- 索引不够完善
- 缺少数据归档机制
- 预聚合表结构需要优化
*/

-- ============================================================
-- 二、核心表结构优化
-- ============================================================

-- 2.1 device_info 设备信息主表优化
-- 添加索引,优化区域查询

ALTER TABLE `device_info`
    -- 添加复合索引优化账户+区域查询
    ADD INDEX `idx_account_area` (`账户`, `区域1`, `区域2`, `区域3`),
    -- 添加设备号唯一索引(如果不存在)
    ADD UNIQUE INDEX `idx_device_id` (`设备号`),
    -- 添加日期索引
    ADD INDEX `idx_date` (`日期`),
    -- 添加区域索引(支持区域筛选)
    ADD INDEX `idx_area1` (`区域1`),
    ADD INDEX `idx_area2` (`区域2`),
    ADD INDEX `idx_area3` (`区域3`);

-- 2.2 创建设备状态实时表(替代频繁查询device_info)
-- 用于快速获取设备在线状态和最新数据时间

CREATE TABLE IF NOT EXISTS `device_status_realtime` (
    `设备号` VARCHAR(50) NOT NULL,
    `账户` VARCHAR(50) NOT NULL DEFAULT '',
    `在线状态` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1:在线, 0:离线',
    `最新数据时间` DATETIME NULL,
    `当前功率` INT NULL DEFAULT 0,
    `当前电能` INT NULL DEFAULT 0,
    `区域1` VARCHAR(100) NULL DEFAULT '',
    `区域2` VARCHAR(100) NULL DEFAULT '',
    `区域3` VARCHAR(100) NULL DEFAULT '',
    `更新时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`设备号`),
    INDEX `idx_account_online` (`账户`, `在线状态`),
    INDEX `idx_account_area` (`账户`, `区域1`, `区域2`, `区域3`),
    INDEX `idx_update_time` (`更新时间`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备实时状态表';

-- 2.3 创建区域统计缓存表(加速区域筛选统计)

CREATE TABLE IF NOT EXISTS `area_statistics_cache` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `账户` VARCHAR(50) NOT NULL DEFAULT '',
    `区域路径` VARCHAR(255) NOT NULL COMMENT '格式:区域1/区域2/区域3',
    `设备总数` INT NOT NULL DEFAULT 0,
    `在线设备数` INT NOT NULL DEFAULT 0,
    `离线设备数` INT NOT NULL DEFAULT 0,
    `总功率` BIGINT NOT NULL DEFAULT 0,
    `更新时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT TIMESTAMP,
    UNIQUE INDEX `idx_account_area` (`账户`, `区域路径`),
    INDEX `idx_account` (`账户`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='区域统计缓存表';

-- ============================================================
-- 三、设备数据表优化(解决5000-10000个表的问题)
-- ============================================================

-- 3.1 创建统一设备原始数据表(分区表)
-- 替代每个设备一个表的设计,使用分区提高性能

CREATE TABLE IF NOT EXISTS `device_data_raw` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `设备号` VARCHAR(50) NOT NULL,
    `账户` VARCHAR(50) NOT NULL DEFAULT '',
    `SV` VARCHAR(25) NULL,
    `CT` VARCHAR(25) NULL,
    `datetime` DATETIME NOT NULL,
    `data` JSON NULL,
    `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`, `datetime`),
    INDEX `idx_device_time` (`设备号`, `datetime`),
    INDEX `idx_device_sv_ct` (`设备号`, `SV`, `CT`),
    INDEX `idx_datetime` (`datetime`),
    INDEX `idx_account` (`账户`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
PARTITION BY RANGE COLUMNS(`datetime`) (
    PARTITION p2024_01 VALUES LESS THAN ('2024-02-01'),
    PARTITION p2024_02 VALUES LESS THAN ('2024-03-01'),
    PARTITION p2024_03 VALUES LESS THAN ('2024-04-01'),
    PARTITION p2024_04 VALUES LESS THAN ('2024-05-01'),
    PARTITION p2024_05 VALUES LESS THAN ('2024-06-01'),
    PARTITION p2024_06 VALUES LESS THAN ('2024-07-01'),
    PARTITION p2024_07 VALUES LESS THAN ('2024-08-01'),
    PARTITION p2024_08 VALUES LESS THAN ('2024-09-01'),
    PARTITION p2024_09 VALUES LESS THAN ('2024-10-01'),
    PARTITION p2024_10 VALUES LESS THAN ('2024-11-01'),
    PARTITION p2024_11 VALUES LESS THAN ('2024-12-01'),
    PARTITION p2024_12 VALUES LESS THAN ('2025-01-01'),
    PARTITION p2025_01 VALUES LESS THAN ('2025-02-01'),
    PARTITION p2025_02 VALUES LESS THAN ('2025-03-01'),
    PARTITION p2025_03 VALUES LESS THAN ('2025-04-01'),
    PARTITION p2025_04 VALUES LESS THAN ('2025-05-01'),
    PARTITION p2025_05 VALUES LESS THAN ('2025-06-01'),
    PARTITION p2025_06 VALUES LESS THAN ('2025-07-01'),
    PARTITION p2025_07 VALUES LESS THAN ('2025-08-01'),
    PARTITION p2025_08 VALUES LESS THAN ('2025-09-01'),
    PARTITION p2025_09 VALUES LESS THAN ('2025-10-01'),
    PARTITION p2025_10 VALUES LESS THAN ('2025-11-01'),
    PARTITION p2025_11 VALUES LESS THAN ('2025-12-01'),
    PARTITION p2025_12 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION p2026_04 VALUES LESS THAN ('2026-05-01'),
    PARTITION p2026_05 VALUES LESS THAN ('2026-06-01'),
    PARTITION p2026_06 VALUES LESS THAN ('2026-07-01'),
    PARTITION p2026_07 VALUES LESS THAN ('2026-08-01'),
    PARTITION p2026_08 VALUES LESS THAN ('2026-09-01'),
    PARTITION p2026_09 VALUES LESS THAN ('2026-10-01'),
    PARTITION p2026_10 VALUES LESS THAN ('2026-11-01'),
    PARTITION p2026_11 VALUES LESS THAN ('2026-12-01'),
    PARTITION p2026_12 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);

-- 3.2 创建统一设备解析数据表(分区表)

CREATE TABLE IF NOT EXISTS `device_data_parsed` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `设备号` VARCHAR(50) NOT NULL,
    `账户` VARCHAR(50) NOT NULL DEFAULT '',
    `日期` DATE NOT NULL,
    `最新时间` DATETIME NOT NULL,
    `最低累计电能` INT NOT NULL DEFAULT 0,
    `最高累计电能` INT NOT NULL DEFAULT 0,
    `当天累计电能` INT NOT NULL DEFAULT 0,
    `在线情况` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1:在线, 0:离线',
    `告警条数` INT NOT NULL DEFAULT 0,
    `告警内容` TEXT NOT NULL,
    `功率` INT NOT NULL DEFAULT 0,
    `功率时间` DATETIME NULL,
    `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`, `日期`),
    UNIQUE INDEX `idx_device_date` (`设备号`, `日期`),
    INDEX `idx_date` (`日期`),
    INDEX `idx_account` (`账户`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
PARTITION BY RANGE COLUMNS(`日期`) (
    PARTITION p2024_01 VALUES LESS THAN ('2024-02-01'),
    PARTITION p2024_02 VALUES LESS THAN ('2024-03-01'),
    PARTITION p2024_03 VALUES LESS THAN ('2024-04-01'),
    PARTITION p2024_04 VALUES LESS THAN ('2024-05-01'),
    PARTITION p2024_05 VALUES LESS THAN ('2024-06-01'),
    PARTITION p2024_06 VALUES LESS THAN ('2024-07-01'),
    PARTITION p2024_07 VALUES LESS THAN ('2024-08-01'),
    PARTITION p2024_08 VALUES LESS THAN ('2024-09-01'),
    PARTITION p2024_09 VALUES LESS THAN ('2024-10-01'),
    PARTITION p2024_10 VALUES LESS THAN ('2024-11-01'),
    PARTITION p2024_11 VALUES LESS THAN ('2024-12-01'),
    PARTITION p2024_12 VALUES LESS THAN ('2025-01-01'),
    PARTITION p2025_01 VALUES LESS THAN ('2025-02-01'),
    PARTITION p2025_02 VALUES LESS THAN ('2025-03-01'),
    PARTITION p2025_03 VALUES LESS THAN ('2025-04-01'),
    PARTITION p2025_04 VALUES LESS THAN ('2025-05-01'),
    PARTITION p2025_05 VALUES LESS THAN ('2025-06-01'),
    PARTITION p2025_06 VALUES LESS THAN ('2025-07-01'),
    PARTITION p2025_07 VALUES LESS THAN ('2025-08-01'),
    PARTITION p2025_08 VALUES LESS THAN ('2025-09-01'),
    PARTITION p2025_09 VALUES LESS THAN ('2025-10-01'),
    PARTITION p2025_10 VALUES LESS THAN ('2025-11-01'),
    PARTITION p2025_11 VALUES LESS THAN ('2025-12-01'),
    PARTITION p2025_12 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION p2026_04 VALUES LESS THAN ('2026-05-01'),
    PARTITION p2026_05 VALUES LESS THAN ('2026-06-01'),
    PARTITION p2026_06 VALUES LESS THAN ('2026-07-01'),
    PARTITION p2026_07 VALUES LESS THAN ('2026-08-01'),
    PARTITION p2026_08 VALUES LESS THAN ('2026-09-01'),
    PARTITION p2026_09 VALUES LESS THAN ('2026-10-01'),
    PARTITION p2026_10 VALUES LESS THAN ('2026-11-01'),
    PARTITION p2026_11 VALUES LESS THAN ('2026-12-01'),
    PARTITION p2026_12 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);

-- 3.3 创建统一设备功率记录表(分区表)

CREATE TABLE IF NOT EXISTS `device_data_power` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `设备号` VARCHAR(50) NOT NULL,
    `账户` VARCHAR(50) NOT NULL DEFAULT '',
    `时间点` DATETIME NOT NULL,
    `功率` INT NULL DEFAULT NULL COMMENT 'NULL表示无数据, 0表示功率为0',
    `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`, `时间点`),
    UNIQUE INDEX `idx_device_time` (`设备号`, `时间点`),
    INDEX `idx_time` (`时间点`),
    INDEX `idx_account` (`账户`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
PARTITION BY RANGE COLUMNS(`时间点`) (
    PARTITION p2024_01 VALUES LESS THAN ('2024-02-01'),
    PARTITION p2024_02 VALUES LESS THAN ('2024-03-01'),
    PARTITION p2024_03 VALUES LESS THAN ('2024-04-01'),
    PARTITION p2024_04 VALUES LESS THAN ('2024-05-01'),
    PARTITION p2024_05 VALUES LESS THAN ('2024-06-01'),
    PARTITION p2024_06 VALUES LESS THAN ('2024-07-01'),
    PARTITION p2024_07 VALUES LESS THAN ('2024-08-01'),
    PARTITION p2024_08 VALUES LESS THAN ('2024-09-01'),
    PARTITION p2024_09 VALUES LESS THAN ('2024-10-01'),
    PARTITION p2024_10 VALUES LESS THAN ('2024-11-01'),
    PARTITION p2024_11 VALUES LESS THAN ('2024-12-01'),
    PARTITION p2024_12 VALUES LESS THAN ('2025-01-01'),
    PARTITION p2025_01 VALUES LESS THAN ('2025-02-01'),
    PARTITION p2025_02 VALUES LESS THAN ('2025-03-01'),
    PARTITION p2025_03 VALUES LESS THAN ('2025-04-01'),
    PARTITION p2025_04 VALUES LESS THAN ('2025-05-01'),
    PARTITION p2025_05 VALUES LESS THAN ('2025-06-01'),
    PARTITION p2025_06 VALUES LESS THAN ('2025-07-01'),
    PARTITION p2025_07 VALUES LESS THAN ('2025-08-01'),
    PARTITION p2025_08 VALUES LESS THAN ('2025-09-01'),
    PARTITION p2025_09 VALUES LESS THAN ('2025-10-01'),
    PARTITION p2025_10 VALUES LESS THAN ('2025-11-01'),
    PARTITION p2025_11 VALUES LESS THAN ('2025-12-01'),
    PARTITION p2025_12 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION p2026_04 VALUES LESS THAN ('2026-05-01'),
    PARTITION p2026_05 VALUES LESS THAN ('2026-06-01'),
    PARTITION p2026_06 VALUES LESS THAN ('2026-07-01'),
    PARTITION p2026_07 VALUES LESS THAN ('2026-08-01'),
    PARTITION p2026_08 VALUES LESS THAN ('2026-09-01'),
    PARTITION p2026_09 VALUES LESS THAN ('2026-10-01'),
    PARTITION p2026_10 VALUES LESS THAN ('2026-11-01'),
    PARTITION p2026_11 VALUES LESS THAN ('2026-12-01'),
    PARTITION p2026_12 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);

-- ============================================================
-- 四、预聚合表优化
-- ============================================================

-- 4.1 优化summary_power表 - 添加更多索引

ALTER TABLE `summary_power`
    ADD INDEX `idx_time_account` (`时间点`, `账户`),
    ADD INDEX `idx_online_devices` (`在线设备数`);

-- 4.2 优化summary_power_by_area表

ALTER TABLE `summary_power_by_area`
    ADD INDEX `idx_area_time` (`区域路径`, `时间点`),
    ADD INDEX `idx_account_area` (`账户`, `区域路径`);

-- 4.3 创建小时级功率汇总表(用于24小时功率图表)

CREATE TABLE IF NOT EXISTS `summary_hourly_power` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `账户` VARCHAR(50) NOT NULL DEFAULT '',
    `区域路径` VARCHAR(255) NOT NULL DEFAULT 'ALL' COMMENT 'ALL表示全部区域',
    `小时` DATETIME NOT NULL COMMENT '整点小时,如 2024-01-01 14:00:00',
    `设备数` INT NOT NULL DEFAULT 0,
    `功率之和` BIGINT NOT NULL DEFAULT 0,
    `在线设备数` INT NOT NULL DEFAULT 0,
    `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX `idx_account_area_hour` (`账户`, `区域路径`, `小时`),
    INDEX `idx_hour` (`小时`),
    INDEX `idx_account` (`账户`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='小时级功率汇总表';

-- 4.4 创建设备在线历史记录表(用于7天在线率精确计算)

CREATE TABLE IF NOT EXISTS `device_online_history` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `设备号` VARCHAR(50) NOT NULL,
    `账户` VARCHAR(50) NOT NULL DEFAULT '',
    `日期` DATE NOT NULL,
    `在线状态` TINYINT(1) NOT NULL DEFAULT 0,
    `首次上线时间` DATETIME NULL,
    `最后上线时间` DATETIME NULL,
    `在线时长分钟` INT NOT NULL DEFAULT 0,
    `数据条数` INT NOT NULL DEFAULT 0,
    `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE INDEX `idx_device_date` (`设备号`, `日期`),
    INDEX `idx_date` (`日期`),
    INDEX `idx_account` (`账户`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备在线历史记录表';

-- ============================================================
-- 五、数据归档和清理优化
-- ============================================================

-- 5.1 创建归档表(用于存储历史数据)

CREATE TABLE IF NOT EXISTS `device_data_raw_archive` (
    `id` BIGINT UNSIGNED NOT NULL,
    `设备号` VARCHAR(50) NOT NULL,
    `账户` VARCHAR(50) NOT NULL DEFAULT '',
    `SV` VARCHAR(25) NULL,
    `CT` VARCHAR(25) NULL,
    `datetime` DATETIME NOT NULL,
    `data` JSON NULL,
    `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_device_time` (`设备号`, `datetime`),
    INDEX `idx_datetime` (`datetime`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备原始数据归档表';

-- 5.2 创建数据清理日志表

CREATE TABLE IF NOT EXISTS `data_cleanup_log` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `清理类型` VARCHAR(50) NOT NULL COMMENT 'raw/parsed/power',
    `清理日期范围` VARCHAR(100) NOT NULL,
    `清理记录数` INT NOT NULL DEFAULT 0,
    `清理前数据量` BIGINT NOT NULL DEFAULT 0,
    `清理后数据量` BIGINT NOT NULL DEFAULT 0,
    `执行时间` INT NOT NULL DEFAULT 0 COMMENT '执行耗时(秒)',
    `执行状态` VARCHAR(20) NOT NULL DEFAULT 'success',
    `错误信息` TEXT NULL,
    `创建时间` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据清理日志表';

-- ============================================================
-- 六、存储过程和函数优化
-- ============================================================

-- 6.1 创建批量插入存储过程(提高数据写入性能)

DELIMITER //

CREATE PROCEDURE IF NOT EXISTS `sp_batch_insert_raw_data`(
    IN p_json_data TEXT  -- JSON数组格式的数据
)
BEGIN
    DECLARE v_idx INT DEFAULT 0;
    DECLARE v_count INT;
    DECLARE v_item JSON;
    
    -- 解析JSON数组
    SET v_count = JSON_LENGTH(p_json_data);
    
    WHILE v_idx < v_count DO
        SET v_item = JSON_EXTRACT(p_json_data, CONCAT('$[', v_idx, ']'));
        
        INSERT INTO `device_data_raw` (`设备号`, `账户`, `SV`, `CT`, `datetime`, `data`)
        VALUES (
            JSON_UNQUOTE(JSON_EXTRACT(v_item, '$.device_id')),
            JSON_UNQUOTE(JSON_EXTRACT(v_item, '$.account')),
            JSON_UNQUOTE(JSON_EXTRACT(v_item, '$.sv')),
            JSON_UNQUOTE(JSON_EXTRACT(v_item, '$.ct')),
            JSON_UNQUOTE(JSON_EXTRACT(v_item, '$.datetime')),
            JSON_EXTRACT(v_item, '$.data')
        );
        
        SET v_idx = v_idx + 1;
    END WHILE;
END //

-- 6.2 创建区域统计更新存储过程

CREATE PROCEDURE IF NOT EXISTS `sp_update_area_statistics`(
    IN p_account VARCHAR(50)
)
BEGIN
    -- 清空该账户的缓存
    DELETE FROM `area_statistics_cache` WHERE `账户` = p_account;
    
    -- 重新计算区域统计
    INSERT INTO `area_statistics_cache` (`账户`, `区域路径`, `设备总数`, `在线设备数`, `离线设备数`, `总功率`)
    SELECT 
        p_account,
        COALESCE(`区域路径`, '未分类'),
        COUNT(*),
        SUM(`在线状态`),
        COUNT(*) - SUM(`在线状态`),
        SUM(`当前功率`)
    FROM `device_status_realtime`
    WHERE `账户` = p_account
    GROUP BY `区域路径`;
END //

-- 6.3 创建数据归档存储过程

CREATE PROCEDURE IF NOT EXISTS `sp_archive_old_data`(
    IN p_days INT  -- 归档多少天前的数据
)
BEGIN
    DECLARE v_cutoff_date DATE;
    DECLARE v_archived_count INT DEFAULT 0;
    DECLARE v_start_time DATETIME;
    
    SET v_cutoff_date = DATE_SUB(CURDATE(), INTERVAL p_days DAY);
    SET v_start_time = NOW();
    
    -- 开始事务
    START TRANSACTION;
    
    -- 归档原始数据
    INSERT INTO `device_data_raw_archive`
    SELECT * FROM `device_data_raw`
    WHERE `datetime` < v_cutoff_date;
    
    SET v_archived_count = ROW_COUNT();
    
    -- 删除已归档的原始数据
    DELETE FROM `device_data_raw`
    WHERE `datetime` < v_cutoff_date;
    
    -- 记录日志
    INSERT INTO `data_cleanup_log` 
        (`清理类型`, `清理日期范围`, `清理记录数`, `执行时间`, `执行状态`)
    VALUES 
        ('raw', CONCAT('< ', v_cutoff_date), v_archived_count, 
         TIMESTAMPDIFF(SECOND, v_start_time, NOW()), 'success');
    
    COMMIT;
END //

DELIMITER ;

-- ============================================================
-- 七、触发器优化
-- ============================================================

-- 7.1 创建设备状态实时更新触发器
-- 当device_data_parsed表更新时,同步更新device_status_realtime

DELIMITER //

CREATE TRIGGER IF NOT EXISTS `trg_update_device_status`
AFTER INSERT ON `device_data_parsed`
FOR EACH ROW
BEGIN
    INSERT INTO `device_status_realtime` 
        (`设备号`, `账户`, `在线状态`, `最新数据时间`, `当前功率`, `功率时间`, `区域1`, `区域2`, `区域3`)
    SELECT 
        NEW.`设备号`,
        d.`账户`,
        NEW.`在线情况`,
        NEW.`最新时间`,
        NEW.`功率`,
        NEW.`功率时间`,
        d.`区域1`,
        d.`区域2`,
        d.`区域3`
    FROM `device_info` d
    WHERE d.`设备号` = NEW.`设备号`
    ON DUPLICATE KEY UPDATE
        `在线状态` = NEW.`在线情况`,
        `最新数据时间` = NEW.`最新时间`,
        `当前功率` = NEW.`功率`,
        `功率时间` = NEW.`功率时间`;
END //

-- 7.2 创建设备区域变更触发器
-- 当device_info的区域信息变更时,同步更新device_status_realtime

CREATE TRIGGER IF NOT EXISTS `trg_update_device_area`
AFTER UPDATE ON `device_info`
FOR EACH ROW
BEGIN
    IF OLD.`区域1` != NEW.`区域1` OR OLD.`区域2` != NEW.`区域2` OR OLD.`区域3` != NEW.`区域3` THEN
        UPDATE `device_status_realtime`
        SET `区域1` = NEW.`区域1`,
            `区域2` = NEW.`区域2`,
            `区域3` = NEW.`区域3`
        WHERE `设备号` = NEW.`设备号`;
    END IF;
END //

DELIMITER ;

-- ============================================================
-- 八、视图优化
-- ============================================================

-- 8.1 创建设备完整信息视图

CREATE OR REPLACE VIEW `v_device_full_info` AS
SELECT 
    d.`设备号`,
    d.`设备名称`,
    d.`账户`,
    d.`日期`,
    d.`区域1`,
    d.`区域2`,
    d.`区域3`,
    CONCAT_WS('/', NULLIF(d.`区域1`, ''), NULLIF(d.`区域2`, ''), NULLIF(d.`区域3`, '')) AS `区域路径`,
    d.`相对X`,
    d.`相对Y`,
    d.`工作计划`,
    s.`在线状态`,
    s.`最新数据时间`,
    s.`当前功率`,
    s.`当前电能`
FROM `device_info` d
LEFT JOIN `device_status_realtime` s ON d.`设备号` = s.`设备号`;

-- 8.2 创建区域设备统计视图

CREATE OR REPLACE VIEW `v_area_device_stats` AS
SELECT 
    `账户`,
    `区域路径`,
    COUNT(*) AS `设备总数`,
    SUM(`在线状态`) AS `在线设备数`,
    COUNT(*) - SUM(`在线状态`) AS `离线设备数`,
    SUM(`当前功率`) AS `总功率`,
    ROUND(SUM(`在线状态`) / COUNT(*) * 100, 2) AS `在线率`
FROM `device_status_realtime`
GROUP BY `账户`, `区域路径`;

-- ============================================================
-- 九、数据迁移脚本(从旧表结构迁移到新表结构)
-- ============================================================

/*
-- 9.1 迁移设备原始数据(分批执行,避免锁表)
-- 注意: 这是一个示例,实际执行时需要根据设备数量分批处理

INSERT INTO `device_data_raw` (`设备号`, `账户`, `SV`, `CT`, `datetime`, `data`)
SELECT `设备号`, '', `SV`, `CT`, `datetime`, `data`
FROM `{device_id}`
WHERE `datetime` >= '2024-01-01';

-- 9.2 迁移设备解析数据
INSERT INTO `device_data_parsed` (`设备号`, `账户`, `日期`, `最新时间`, `最低累计电能`, `最高累计电能`, `当天累计电能`, `在线情况`, `告警条数`, `告警内容`, `功率`, `功率时间`)
SELECT `设备号`, '', `日期`, `最新时间`, `最低累计电能`, `最高累计电能`, `当天累计电能`, `在线情况`, `告警条数`, `告警内容`, `功率`, `功率时间`
FROM `{device_id}_parsed`;

-- 9.3 迁移设备功率数据
INSERT INTO `device_data_power` (`设备号`, `账户`, `时间点`, `功率`)
SELECT `设备号`, '', `时间点`, `功率`
FROM `{device_id}_power`;
*/

-- ============================================================
-- 十、性能监控表
-- ============================================================

CREATE TABLE IF NOT EXISTS `db_performance_log` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `监控项` VARCHAR(100) NOT NULL,
    `监控值` DECIMAL(18, 4) NOT NULL,
    `监控单位` VARCHAR(20) NOT NULL,
    `采样时间` DATETIME NOT NULL,
    `备注` VARCHAR(255) NULL,
    INDEX `idx_item_time` (`监控项`, `采样时间`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据库性能监控日志';

-- ============================================================
-- 十一、定期维护任务建议
-- ============================================================

/*
建议配置以下定期任务:

1. 每小时执行 - 更新区域统计缓存
   CALL sp_update_area_statistics('all_accounts');

2. 每天凌晨2点执行 - 数据归档
   CALL sp_archive_old_data(90);  -- 归档90天前的数据

3. 每周执行 - 优化表
   OPTIMIZE TABLE device_data_raw;
   OPTIMIZE TABLE device_data_parsed;
   OPTIMIZE TABLE device_data_power;

4. 每月执行 - 添加新的分区
   ALTER TABLE device_data_raw ADD PARTITION (
       PARTITION p2027_01 VALUES LESS THAN ('2027-02-01')
   );

5. 实时监控 - 记录表大小
   INSERT INTO db_performance_log (监控项, 监控值, 监控单位, 采样时间)
   SELECT 
       CONCAT(table_name, '_size'),
       ROUND((data_length + index_length) / 1024 / 1024, 2),
       'MB',
       NOW()
   FROM information_schema.tables
   WHERE table_schema = 'MST_SQL';
*/

-- ============================================================
-- 十二、回滚脚本(如需回滚到旧结构)
-- ============================================================

/*
-- 如果需要回滚,执行以下脚本:

-- 删除新表
DROP TABLE IF EXISTS `device_data_raw`;
DROP TABLE IF EXISTS `device_data_parsed`;
DROP TABLE IF EXISTS `device_data_power`;
DROP TABLE IF EXISTS `device_status_realtime`;
DROP TABLE IF EXISTS `area_statistics_cache`;
DROP TABLE IF EXISTS `summary_hourly_power`;
DROP TABLE IF EXISTS `device_online_history`;
DROP TABLE IF EXISTS `device_data_raw_archive`;
DROP TABLE IF EXISTS `data_cleanup_log`;
DROP TABLE IF EXISTS `db_performance_log`;

-- 删除触发器
DROP TRIGGER IF EXISTS `trg_update_device_status`;
DROP TRIGGER IF EXISTS `trg_update_device_area`;

-- 删除存储过程
DROP PROCEDURE IF EXISTS `sp_batch_insert_raw_data`;
DROP PROCEDURE IF EXISTS `sp_update_area_statistics`;
DROP PROCEDURE IF EXISTS `sp_archive_old_data`;

-- 删除视图
DROP VIEW IF EXISTS `v_device_full_info`;
DROP VIEW IF EXISTS `v_area_device_stats`;

-- 恢复device_info表的索引
ALTER TABLE `device_info` DROP INDEX `idx_account_area`;
ALTER TABLE `device_info` DROP INDEX `idx_device_id`;
ALTER TABLE `device_info` DROP INDEX `idx_date`;
ALTER TABLE `device_info` DROP INDEX `idx_area1`;
ALTER TABLE `device_info` DROP INDEX `idx_area2`;
ALTER TABLE `device_info` DROP INDEX `idx_area3`;
*/
