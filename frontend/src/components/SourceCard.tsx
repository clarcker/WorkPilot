import { Collapse, Tag, Typography } from 'antd'
import { FileTextOutlined } from '@ant-design/icons'
import type { Source } from '../types'

const { Text, Paragraph } = Typography

interface Props {
  sources: Source[]
}

const LIFECYCLE_LABELS: Record<string, { label: string; color: string }> = {
  effective:  { label: '现行', color: 'green' },
  superseded: { label: '已替代', color: 'orange' },
  draft:      { label: '草案', color: 'purple' },
}

export default function SourceCard({ sources }: Props) {
  if (!sources || sources.length === 0) return null

  const items = sources.map((src, idx) => {
    // 构建位置信息
    const locationParts: string[] = []
    if (src.heading) locationParts.push(src.heading)
    if (src.page_no) locationParts.push(`第${src.page_no}页`)
    const location = locationParts.length > 0 ? locationParts.join(' > ') : null
    const life = src.lifecycle && LIFECYCLE_LABELS[src.lifecycle]
      ? LIFECYCLE_LABELS[src.lifecycle]
      : null

    return {
      key: String(idx),
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <FileTextOutlined style={{ color: '#1677ff' }} />
          <Text strong style={{ fontSize: 13 }}>{src.doc_name || '未知文档'}</Text>
          {life && <Tag color={life.color} style={{ fontSize: 11 }}>{life.label}</Tag>}
          {src.effective_date && (
            <Text type="secondary" style={{ fontSize: 11 }}>{src.effective_date}</Text>
          )}
          {location && (
            <Text type="secondary" style={{ fontSize: 11 }}>{location}</Text>
          )}
          <Tag color="blue" style={{ marginLeft: 'auto', fontSize: 11 }}>
            相关度 {Math.round(src.score * 100)}%
          </Tag>
        </span>
      ),
      children: (
        <>
          {src.lifecycle_note && (
            <Paragraph type="warning" style={{ fontSize: 12, marginBottom: 6 }}>
              {src.lifecycle_note}
            </Paragraph>
          )}
          {src.chunk_text ? (
            <Paragraph
              style={{
                fontSize: 13,
                color: '#555',
                margin: 0,
                padding: '4px 0',
                borderLeft: '3px solid #1677ff',
                paddingLeft: 10,
                lineHeight: 1.7,
              }}
            >
              {src.chunk_text.length > 300
                ? src.chunk_text.slice(0, 300) + '...'
                : src.chunk_text}
            </Paragraph>
          ) : null}
        </>
      ),
    }
  })

  return (
    <Collapse
      ghost
      size="small"
      style={{ marginTop: 8, background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0' }}
      items={items}
    />
  )
}
