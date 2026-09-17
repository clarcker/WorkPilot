/**
 * SystemLogsTab — 系统运行日志
 */
import dayjs from 'dayjs'
import { useEffect, useState, useCallback } from 'react'
import {
  Button, Table, Tag, Space, Input, Select, Typography, message as antMsg,
  DatePicker, Alert,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { getSystemLogs, type LogEntry } from '../../api/admin'

const { Text, Title } = Typography

const LOG_LEVEL_COLORS: Record<string, string> = {
  DEBUG:     'default',
  INFO:      'blue',
  WARNING:   'orange',
  ERROR:     'red',
  CRITICAL:  'magenta',
}

export default function SystemLogsTab() {
  const [logs, setLogs]             = useState<LogEntry[]>([])
  const [total, setTotal]           = useState(0)
  const [page, setPage]             = useState(1)
  const [loading, setLoading]       = useState(false)
  const [logDate, setLogDate]       = useState<string>(dayjs().format('YYYY-MM-DD'))
  const [filterLevel, setFilterLevel] = useState<string>('')
  const [keyword, setKeyword]       = useState<string>('')
  const [fileExists, setFileExists] = useState(true)

  const load = useCallback(async (p = page, date = logDate, level = filterLevel, kw = keyword) => {
    setLoading(true)
    try {
      const res = await getSystemLogs({
        log_date: date,
        level: level || undefined,
        keyword: kw || undefined,
        page: p,
        page_size: 100,
      })
      setLogs(res.items)
      setTotal(res.total)
      setFileExists(res.file_exists)
    } catch {
      antMsg.error('加载日志失败')
    } finally {
      setLoading(false)
    }
  }, [page, logDate, filterLevel, keyword])

  useEffect(() => { load() }, [load])

  function handleDateChange(date: dayjs.Dayjs | null) {
    const d = date ? date.format('YYYY-MM-DD') : dayjs().format('YYYY-MM-DD')
    setLogDate(d)
    setPage(1)
    load(1, d, filterLevel, keyword)
  }

  function handleLevelChange(level: string) {
    setFilterLevel(level)
    setPage(1)
    load(1, logDate, level, keyword)
  }

  function handleSearch(kw: string) {
    setKeyword(kw)
    setPage(1)
    load(1, logDate, filterLevel, kw)
  }

  const cols = [
    { title: '时间', dataIndex: 'timestamp', key: 'timestamp', width: 190,
      render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text> },
    { title: '级别', dataIndex: 'level', key: 'level', width: 90,
      render: (v: string) => <Tag color={LOG_LEVEL_COLORS[v] ?? 'default'}>{v}</Tag> },
    { title: '位置', dataIndex: 'location', key: 'location', width: 200,
      render: (v: string) => <Text type="secondary" ellipsis style={{ fontSize: 12, maxWidth: 180 }}>{v}</Text> },
    { title: '请求ID', dataIndex: 'request_id', key: 'request_id', width: 100,
      render: (v: string) => v ? <Text code style={{ fontSize: 11 }}>{v}</Text> : '—' },
    { title: '消息', dataIndex: 'message', key: 'message', ellipsis: true },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <Title level={5} style={{ margin: 0 }}>系统日志</Title>
        <Space wrap>
          <DatePicker
            defaultValue={dayjs()}
            onChange={handleDateChange}
            allowClear={false}
            style={{ width: 150 }}
          />
          <Select
            value={filterLevel || undefined}
            onChange={handleLevelChange}
            placeholder="日志级别"
            allowClear
            style={{ width: 120 }}
          >
            <Select.Option value="DEBUG">DEBUG</Select.Option>
            <Select.Option value="INFO">INFO</Select.Option>
            <Select.Option value="WARNING">WARNING</Select.Option>
            <Select.Option value="ERROR">ERROR</Select.Option>
            <Select.Option value="CRITICAL">CRITICAL</Select.Option>
          </Select>
          <Input.Search
            placeholder="关键词搜索"
            allowClear
            style={{ width: 200 }}
            onSearch={handleSearch}
          />
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
        </Space>
      </div>

      {!fileExists ? (
        <Alert
          type="info"
          showIcon
          message={`${logDate} 的日志文件不存在`}
          style={{ marginBottom: 16 }}
        />
      ) : (
        <Table
          dataSource={logs} columns={cols} rowKey={(_, i) => String(i)} loading={loading} size="small"
          pagination={{
            current: page, pageSize: 100, total,
            onChange: (p) => { setPage(p); load(p) },
            showTotal: (t) => `共 ${t} 条`,
            showSizeChanger: false,
          }}
          scroll={{ x: 900 }}
        />
      )}
    </div>
  )
}
