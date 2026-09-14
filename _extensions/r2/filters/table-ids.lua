-- Pandoc's LaTeX reader wraps labelled tables in Divs. The JATS writer
-- drops those wrapper IDs, leaving dangling table cross-references.
-- Attach the identifier to the table itself in all output formats.
function Div(el)
  if el.identifier == '' or #el.content ~= 1 or el.content[1].t ~= 'Table' then
    return nil
  end
  local tbl = el.content[1]
  if tbl.identifier == '' then
    tbl.identifier = el.identifier
    return tbl
  end
end

-- Auto-width columns become non-wrapping `l` columns in LaTeX. Assign
-- proportional widths to text-heavy tables so every cell stays on the page.
function Table(tbl)
  if #tbl.colspecs < 3 then return nil end
  local lengths, total = {}, 0
  for i=1,#tbl.colspecs do lengths[i]=1 end
  local function measure(rows)
    for _,row in ipairs(rows) do
      for i,cell in ipairs(row.cells) do
        lengths[i]=math.max(lengths[i] or 1, #pandoc.utils.stringify(cell.contents))
      end
    end
  end
  measure(tbl.head.rows)
  for _,body in ipairs(tbl.bodies) do measure(body.head); measure(body.body) end
  measure(tbl.foot.rows)
  local automatic=true
  for i,col in ipairs(tbl.colspecs) do
    if col[2] and col[2]>0 then automatic=false end
    total=total+lengths[i]
  end
  if not automatic or total<100 then return nil end
  local weight=0
  for i=1,#tbl.colspecs do lengths[i]=math.sqrt(lengths[i]);weight=weight+lengths[i] end
  for i,col in ipairs(tbl.colspecs) do col[2]=lengths[i]/weight end
  return tbl
end
