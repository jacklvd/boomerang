import { CaretDownIcon, PencilSimpleIcon, ProhibitIcon } from '@phosphor-icons/react/dist/ssr'

import type { ManualField } from '@/src/model/manual-entry'
import { Button } from './button'
import { Heading, Notice } from './primitives'

/**
 * Frame I2 — the manual fallback, for when the retailer's form matched nothing
 * we recognise.
 *
 * The screen submits exactly what the user types. That is the entire value of
 * it, and also why the field allowlist matters more here than anywhere else:
 * this is the one path where the agent's closed action vocabulary is not
 * standing between a page and a keystroke.
 */
export function ManualForm({
  fields,
  values,
  onChange,
  onSubmit,
  onBack,
  refused = [],
}: {
  fields: ManualField[]
  values: Record<string, string>
  onChange: (name: string, value: string) => void
  onSubmit: () => void
  onBack: () => void
  refused?: string[]
}) {
  return (
    <>
      <Chip />
      <Heading
        title="Fill it in yourself"
        body="The retailer's form did not match anything we recognise. Enter it and we will submit exactly what you type."
      />

      {refused.length > 0 && (
        <Notice tone="urgent" icon={<ProhibitIcon size={14} />}>
          {refused.length === 1 ? 'One field was' : `${refused.length} fields were`} left out
          because Boomerang will not type into them. Complete {refused.length === 1 ? 'it' : 'those'}{' '}
          on the retailer's own page.
        </Notice>
      )}

      <div className="flex flex-col gap-3">
        {fields.map((field) => (
          <Field
            key={field.name}
            field={field}
            value={values[field.name] ?? ''}
            onChange={(value) => onChange(field.name, value)}
          />
        ))}
      </div>

      <div className="flex flex-col gap-2.5">
        <Button onClick={onSubmit}>Submit this return</Button>
        <Button variant="ghost" onClick={onBack}>
          Back to the options
        </Button>
      </div>

      <Notice tone="quiet" icon={<ProhibitIcon size={13} className="text-urgent" />}>
        Password, payment and file-upload fields are excluded — manually or not, the agent never
        types into them.
      </Notice>
    </>
  )
}

function Chip() {
  return (
    <span className="flex w-fit items-center gap-2 rounded-full bg-warn-soft px-3 py-1.5">
      <PencilSimpleIcon size={12} className="text-warn" />
      <span className="text-[11.5px] font-semibold tracking-[0.06em] text-warn uppercase">
        Manual entry
      </span>
    </span>
  )
}

const CONTROL =
  'w-full rounded-[10px] border border-line bg-surface px-3 py-2.5 text-[13px] text-ink outline-none focus-visible:border-accent'

function Field({
  field,
  value,
  onChange,
}: {
  field: ManualField
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11.5px] tracking-[0.04em] text-ink-faint uppercase">
        {field.label}
      </span>

      {field.kind === 'choice' ? (
        <span className="relative">
          <select
            value={value}
            onChange={(event) => onChange(event.target.value)}
            className={`${CONTROL} appearance-none pr-9`}
          >
            {field.options?.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <CaretDownIcon
            size={14}
            className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-ink-faint"
          />
        </span>
      ) : field.kind === 'long-text' ? (
        <textarea
          value={value}
          rows={2}
          placeholder={field.placeholder}
          onChange={(event) => onChange(event.target.value)}
          className={`${CONTROL} resize-none placeholder:text-ink-faint`}
        />
      ) : (
        <input
          type="text"
          value={value}
          placeholder={field.placeholder}
          onChange={(event) => onChange(event.target.value)}
          className={`${CONTROL} placeholder:text-ink-faint`}
        />
      )}
    </label>
  )
}
