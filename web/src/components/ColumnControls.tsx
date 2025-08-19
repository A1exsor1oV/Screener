import * as React from 'react'
import { DndContext, PointerSensor, useSensor, useSensors, closestCenter } from '@dnd-kit/core'
import { SortableContext, useSortable, arrayMove, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

type Props = {
  allColumnIds: string[]
  lockedColumnIds?: string[]     // нельзя скрывать/таскать (например 'Акция','Фьючерс','Дата див. отсечки')
  visible: Record<string, boolean>
  setVisible: (next: Record<string, boolean>) => void
  order: string[]
  setOrder: (next: string[]) => void
}

function Row({ id, locked }: { id: string; locked: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id, disabled: locked })
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
    cursor: locked ? 'not-allowed' : 'grab',
  }
  return (
    <div ref={setNodeRef} style={style} className="flex items-center justify-between px-2 py-1 rounded hover:bg-neutral-800/70">
      <span className="text-sm">{id}</span>
      {!locked && <span {...attributes} {...listeners} className="text-xs opacity-60">↕</span>}
    </div>
  )
}

export function ColumnControls({ allColumnIds, lockedColumnIds = [], visible, setVisible, order, setOrder }: Props) {
  const [open, setOpen] = React.useState(false)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))

  function onDragEnd(evt: any) {
    const { active, over } = evt
    if (!over || active.id === over.id) return
    const oldIndex = order.indexOf(active.id)
    const newIndex = order.indexOf(over.id)
    setOrder(arrayMove(order, oldIndex, newIndex))
  }

  function toggle(id: string) {
    if (lockedColumnIds.includes(id)) return
    setVisible({ ...visible, [id]: !visible[id] })
  }

  return (
    <div className="relative">
      <button onClick={() => setOpen(v => !v)} className="px-3 py-2 rounded-md bg-neutral-800 hover:bg-neutral-700 text-sm">
        Столбцы
      </button>
      {open && (
        <div className="absolute z-30 mt-2 w-72 rounded-lg border border-neutral-800 bg-neutral-900 p-2 shadow-lg">
          <div className="max-h-72 overflow-auto space-y-2">
            {/* чекбоксы */}
            <div className="space-y-1">
              {allColumnIds.map(id => (
                <label key={id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={visible[id] ?? true}
                    disabled={lockedColumnIds.includes(id)}
                    onChange={() => toggle(id)}
                  />
                  <span className={lockedColumnIds.includes(id) ? 'opacity-60' : ''}>{id}</span>
                </label>
              ))}
            </div>
            <div className="h-px bg-neutral-800 my-1" />
            {/* drag'n'drop */}
            <div className="text-xs opacity-70 mb-1">Перетаскивание порядка</div>
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
              <SortableContext items={order} strategy={verticalListSortingStrategy}>
                <div className="space-y-1">
                  {order.map(id => (
                    <Row key={id} id={id} locked={lockedColumnIds.includes(id)} />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          </div>
          <div className="text-right mt-2">
            <button onClick={() => setOpen(false)} className="text-sm opacity-70 hover:opacity-100">Закрыть</button>
          </div>
        </div>
      )}
    </div>
  )
}
