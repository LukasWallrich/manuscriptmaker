-- Keep LaTeX figures and section references in Pandoc's native document model.
function Pandoc(doc)
  local sections, counts = {}, {}
  doc = doc:walk({Header=function(h)
    local label = h.identifier
    h.content = h.content:walk({Span=function(span)
      if span.identifier ~= '' then label = span.identifier end
      return span.content
    end})
    if label ~= '' then h.identifier = label end
    if not h.classes:includes('unnumbered') then
      counts[h.level] = (counts[h.level] or 0) + 1
      for i=h.level+1,6 do counts[i]=nil end
      local parts={}
      for i=1,h.level do parts[#parts+1]=tostring(counts[i] or 0) end
      sections[label] = table.concat(parts,'.')
    end
    return h
  end})
  return doc:walk({
    Str=function(el) el.text=el.text:gsub('%-%-%-', '—'):gsub('%-%-', '–'); return el end,
    Figure=function(fig)
      local img
      fig.content:walk({Image=function(el) img=el end})
      if not img then return nil end
      local caption=pandoc.Inlines{}
      for _,block in ipairs(fig.caption.long) do
        if block.content then
          if #caption>0 then caption:insert(pandoc.Space()) end
          caption:extend(block.content)
        end
      end
      caption=caption:walk({Span=function(span) if span.identifier==fig.identifier then return span.content end end})
      img.caption=caption
      img.identifier=fig.identifier
      img.title='fig:'
      return pandoc.Para{img}
    end,
    Link=function(link)
      local id=link.target:match('^#(.+)$')
      if id and sections[id] and link.attributes['reference-type']=='ref' then
        link.content={pandoc.Str(sections[id])}
        link.attributes={}
        return link
      end
    end
  })
end
