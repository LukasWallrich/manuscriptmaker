/* Edit prose blocks while retaining exact source for untouched and complex blocks. */
window.ManuscriptRich = (() => {
  const tokens = /(\[[^\]\n]*@[^\]\n]+\]|\[\^[^\]]+\]|@[\w][\w:./-]*|\$[^$\n]+\$|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\\.)/g;
  function inline(parent, source) {
    let position = 0;
    for (const match of source.matchAll(tokens)) {
      parent.append(document.createTextNode(source.slice(position, match.index)));
      const token = match[0];
      if (token.startsWith('**') || token.startsWith('*')) {
        const width = token.startsWith('**') ? 2 : 1;
        const element = document.createElement(width === 2 ? 'strong' : 'em');
        inline(element, token.slice(width, -width)); parent.append(element);
      } else {
        const element = document.createElement('span');
        element.contentEditable = 'false'; element.dataset.source = token;
        element.className = 'source-token'; element.textContent = token;
        element.title = 'Protected citation, equation or source token; edit in Source mode';
        parent.append(element);
      }
      position = match.index + token.length;
    }
    parent.append(document.createTextNode(source.slice(position)));
  }
  function markdown(node) {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent.replace(/([\\*`\[\]])/g, '\\$1');
    if (node.dataset?.source !== undefined) return node.dataset.source;
    if (node.nodeName === 'BR') return '\n';
    let text = [...node.childNodes].map(markdown).join('');
    if (['B','STRONG'].includes(node.nodeName)) text = '**' + text + '**';
    if (['I','EM'].includes(node.nodeName)) text = '*' + text + '*';
    if (node.nodeName === 'DIV') text = '\n' + text;
    return text;
  }
  function render(root, source, onChange) {
    root.replaceChildren();
    const pieces = source.split(/(\n[ \t]*\n)/);
    const changes = () => onChange(pieces.join(''));
    let codeFence = '', divDepth = 0, displayMath = false;
    pieces.forEach((piece, index) => {
      if (!piece || /^\s*$/.test(piece)) return;
      let structured = Boolean(codeFence || divDepth || displayMath);
      for (const line of piece.split('\n')) {
        const fence = line.match(/^\s*(`{3,}|~{3,})/);
        if (fence) {
          structured = true;
          if (!codeFence) codeFence = fence[1];
          else if (fence[1][0] === codeFence[0] && fence[1].length >= codeFence.length) codeFence = '';
        } else if (!codeFence) {
          if (/^\s*:::/.test(line)) { structured = true; divDepth = /^\s*:::+\s*$/.test(line) ? Math.max(0,divDepth-1) : divDepth+1; }
          if (line.includes('$$')) { structured = true; if ((line.match(/\$\$/g)||[]).length % 2) displayMath = !displayMath; }
        }
      }
      const heading = piece.match(/^(#{1,6}) (.*?)( \{[^\n]*\})?$/s);
      const safe = !structured && !/^(?:\s*[-+*] |\s*\d+[.)] |\s*\||\s*```|\s*:::|\s*<|\s*!\[|\s*\[\^|    |\s*\$\$)/m.test(piece)
        && !/\]\(|\{[^\n]*\}|<\/?[A-Za-z]/.test(heading ? heading[2] : piece);
      if (!safe) {
        const box = document.createElement('details'), summary = document.createElement('summary');
        summary.textContent = /^\s*!\[/.test(piece) ? 'Figure and caption — edit source' : /^\s*\||^\s*:::/m.test(piece) ? 'Table or structured block — edit source' : 'Structured content — edit source';
        const field = document.createElement('textarea');
        field.value = piece; field.setAttribute('aria-label', summary.textContent);
        field.style.height = Math.min(300, Math.max(100, piece.split('\n').length * 24)) + 'px'; field.style.minHeight = '100px';
        field.oninput = () => { pieces[index] = field.value; changes(); };
        box.append(summary, field); root.append(box); return;
      }
      const block = document.createElement(heading ? 'h' + heading[1].length : 'p');
      block.contentEditable = 'true'; block.setAttribute('role','textbox'); block.setAttribute('aria-label','Editable manuscript paragraph');
      inline(block, heading ? heading[2] : piece);
      block.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); document.execCommand('insertLineBreak'); }
      });
      block.addEventListener('paste', event => {
        event.preventDefault(); document.execCommand('insertText', false, event.clipboardData.getData('text/plain'));
      });
      block.oninput = () => {
        const content = markdown(block).replace(/\n$/, '');
        pieces[index] = heading ? heading[1] + ' ' + content + (heading[3] || '') : content;
        changes();
      };
      root.append(block);
    });
  }
  return {render};
})();
