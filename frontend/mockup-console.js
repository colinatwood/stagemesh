(() => {
  const init = () => {
    const root = document.querySelector('.shell');
    const template = document.querySelector('.templatePanel');
    if (!root || !template || document.querySelector('.mockupAppBar')) return;

    const style = document.createElement('style');
    style.textContent = 'body{background:#07111e;color:#e9f2ff}.shell{width:min(1580px,calc(100% - 28px));margin:14px auto;display:flex;flex-direction:column;gap:12px}.mockupAppBar{display:flex;align-items:center;gap:20px;min-height:58px;padding:0 16px;border:1px solid #1a3047;border-radius:10px;background:#08121f}.mockupBrand{display:flex;align-items:center;gap:10px;min-width:235px}.mockupBrandMark{color:#318aff;font-size:24px}.mockupBrand strong,.mockupBrand small{display:block}.mockupBrand small{color:#8fa5bd;font-size:9px;letter-spacing:.09em;text-transform:uppercase}.mockupNav{display:flex;gap:4px;overflow:auto}.mockupNav button{padding:10px 14px;border:0;border-radius:7px;background:transparent;color:#8fa5bd}.mockupNav .active{background:#15365f;color:#fff}.mockupProfile{margin-left:auto;border:1px solid #3b5270;border-radius:50%;padding:9px}.mockupStatus{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.mockupStatus article{display:flex;align-items:center;gap:10px;min-height:62px;padding:10px 13px;border:1px solid #263c54;border-radius:10px;background:#0d1c2c}.mockupStatus .ready{border-color:#35df916b}.mockupStatus .pending{border-color:#f0b94f73}.mockupStatus b{color:#35df91}.mockupStatus .pending b{color:#f0b94f}.mockupStatus strong,.mockupStatus small{display:block}.mockupStatus small{color:#8fa5bd}.mockupGrid{display:grid;grid-template-columns:220px minmax(0,1fr) 270px;gap:10px}.mockupPalette,.mockupCenter,.mockupInspector{border:1px solid #263c54;border-radius:10px;background:#0b1828}.mockupPalette{padding:12px}.mockupPaletteTabs,.mockupInspectorTabs{display:flex;gap:4px;margin-bottom:12px}.mockupPaletteTabs button,.mockupInspectorTabs button{flex:1;padding:8px;border:1px solid #263c54;background:#0d1c2c;color:#8fa5bd}.mockupPaletteTabs .active,.mockupInspectorTabs .active{background:#15365f;color:#fff}.mockupSearch{display:block;margin-bottom:14px;color:#8fa5bd}.mockupSearch input{width:calc(100% - 20px);background:#07111e;border:1px solid #263c54;color:#fff;padding:8px}.mockupPaletteGroup>strong{display:block;margin-bottom:8px;color:#8fa5bd}.mockupPaletteItem{display:flex;gap:8px;width:100%;padding:9px 0;border:0;background:transparent;color:#e9f2ff;text-align:left}.mockupPaletteItem small{display:block;color:#8fa5bd;font-size:9px}.mockupGlyph{color:#318aff}.mockupCenter{padding:12px}.mockupCenter .templateCanvas{min-height:440px}.mockupInspector{padding:14px}.mockupInspector h3{margin:3px 0}.mockupInspector small{color:#8fa5bd}.mockupInspector label{display:block;margin-top:14px;color:#8fa5bd;font-size:10px}.mockupInspector input,.mockupInspector select{display:block;width:100%;margin-top:5px;padding:8px;border:1px solid #263c54;background:#07111e;color:#e9f2ff}.mockupInspectorStatus{margin:12px 0;color:#35df91}.mockupValidated{margin-top:18px;padding:10px;border:1px solid #35df9173;background:#195e412e;color:#35df91}@media(max-width:1050px){.mockupStatus{grid-template-columns:repeat(2,minmax(0,1fr))}.mockupGrid{grid-template-columns:190px minmax(0,1fr)}}@media(max-width:760px){.mockupStatus,.mockupGrid{grid-template-columns:1fr}.mockupNav{display:none}.mockupPalette{display:none}}';
    document.head.appendChild(style);

    const bar = document.createElement('header');
    bar.className = 'mockupAppBar';
    bar.innerHTML = '<div class="mockupBrand"><span class="mockupBrandMark">◆</span><span><strong>StageMesh</strong><small>Live Stage Production Platform</small></span></div><nav class="mockupNav" aria-label="Primary"><button class="active">Stage Editor</button><button>Show Control</button><button>Media</button><button>Templates</button><button>Devices</button><button>Reports</button></nav><span class="mockupProfile" aria-label="Signed in as JD">JD</span>';
    const status = document.createElement('section');
    status.className = 'mockupStatus';
    status.setAttribute('aria-label', 'System readiness');
    status.innerHTML = '<article class="ready"><b>✓</b><div><strong>Software Validated</strong><small>Core application tests passed</small></div></article><article class="ready"><b>✓</b><div><strong>macOS Runtime Validated</strong><small>macOS 14 · Arm64</small></div></article><article class="pending"><b>!</b><div><strong>Physical Loopback Required</strong><small>Connect audio interface for end-to-end test</small></div></article><article class="pending"><b>!</b><div><strong>Browser Testing Required</strong><small>Validate target browsers and devices</small></div></article>';
    root.prepend(status);
    root.prepend(bar);

    const heading = template.querySelector('.sectionHead');
    if (heading) {
      const eyebrow = heading.querySelector('.eyebrow');
      const title = heading.querySelector('h2');
      if (eyebrow) eyebrow.textContent = 'Design workspace';
      if (title) title.textContent = 'Main Stage';
    }

    const toolbar = template.querySelector('.templateToolbar');
    const library = template.querySelector('.templateLibrary');
    const canvas = template.querySelector('#templateCanvas');
    const hint = template.querySelector('#templateHint');
    if (!toolbar || !library || !canvas || !hint) return;

    const grid = document.createElement('div');
    grid.className = 'mockupGrid';
    const palette = document.createElement('aside');
    palette.className = 'mockupPalette';
    palette.innerHTML = '<div class="mockupPaletteTabs"><button class="active">Objects</button><button>Layouts</button></div><label class="mockupSearch">Search objects <input type="search" placeholder="Search objects..." aria-label="Search objects"></label><div class="mockupPaletteGroup"><strong>All objects</strong><button class="mockupPaletteItem" data-type="performer" type="button"><span class="mockupGlyph">●</span><span><b>Performer</b><small>Vocalist, musician, presenter</small></span></button><button class="mockupPaletteItem" data-type="microphone" type="button"><span class="mockupGlyph">◉</span><span><b>Microphone</b><small>Vocal and instrument mic</small></span></button><button class="mockupPaletteItem" data-type="monitor" type="button"><span class="mockupGlyph">◒</span><span><b>Monitor</b><small>Floor monitor and wedge</small></span></button><button class="mockupPaletteItem" data-type="speaker" type="button"><span class="mockupGlyph">◈</span><span><b>Speaker</b><small>PA and side fill</small></span></button><button class="mockupPaletteItem" data-type="light" type="button"><span class="mockupGlyph">✦</span><span><b>Light</b><small>Spot, wash, beam, effect</small></span></button></div>';
    palette.append(library);

    const center = document.createElement('div');
    center.className = 'mockupCenter';
    const tools = document.createElement('div');
    tools.className = 'mockupCanvasToolbar';
    tools.innerHTML = '<span>↖ Select</span><span>✋ Pan</span><span>⌗ Fit</span><span>100%</span>';
    center.append(tools, canvas, toolbar, hint);

    const inspector = document.createElement('aside');
    inspector.className = 'mockupInspector';
    inspector.innerHTML = '<div><span class="eyebrow">Inspector</span><h3>Performer</h3><small>Performer object</small></div><div class="mockupInspectorTabs"><button class="active">Properties</button><button>Connections</button><button>Notes</button></div><div class="mockupInspectorStatus">● Validated</div><label>Label<input value="Performer" readonly></label><label>Position (m)<input value="6.0, 4.0" readonly></label><label>Rotation<input value="0°" readonly></label><label>Scale<select><option>100%</option></select></label><div class="mockupValidated"><strong>✓ Design validated</strong><small>No errors found. Ready for output.</small></div>';
    grid.append(palette, center, inspector);
    template.append(grid);

    palette.querySelectorAll('[data-type]').forEach((button) => button.addEventListener('click', () => {
      const type = document.querySelector('#templateObjectType');
      const label = document.querySelector('#templateObjectLabel');
      if (type) type.value = button.dataset.type;
      if (label) { label.value = button.querySelector('b').textContent; label.focus(); }
    }));
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
