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
