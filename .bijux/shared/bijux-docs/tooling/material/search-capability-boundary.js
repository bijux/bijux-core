/* Read the admitted initial document capability once; native mounts do not replace it. */
const __bijuxSearchCapabilityTarget = (() => {
  const nodes = document.querySelectorAll('meta[name="bijux-csp-navigation"]');
  if (!nodes.length) return () => undefined;
  let base, table, initial;
  try {
    if (nodes.length !== 1 || nodes[0].content.length > 262144) throw new Error('metadata bounds');
    const value = JSON.parse(nodes[0].content);
    if (!value || Array.isArray(value) || Object.keys(value).sort().join(',') !== 'document_partition,document_route,route_partitions,schema,site_url,table_sha256') throw new Error('metadata shape');
    if (value.schema !== 1 || !/^[a-f0-9]{64}$/.test(value.table_sha256)) throw new Error('metadata identity');
    base = new URL(value.site_url);
    if (base.protocol !== 'https:' || base.username || base.password || base.port || base.search || base.hash || !base.pathname.endsWith('/') || base.origin !== location.origin) throw new Error('metadata origin');
    if (!Array.isArray(value.route_partitions) || value.route_partitions.length > 2048) throw new Error('partition bounds');
    const validRoute = route => typeof route === 'string' && route.endsWith('.html') && !/[\u0000-\u0020\u007f%?#\\]/.test(route) && !route.startsWith('/') && !route.split('/').some(p => !p || p === '.' || p === '..');
    if (!validRoute(value.document_route)) throw new Error('document route');
    table = new Map();
    for (const pair of value.route_partitions) {
      if (!Array.isArray(pair) || pair.length !== 2 || !validRoute(pair[0]) || !/^[a-f0-9]{64}$/.test(pair[1]) || table.has(pair[0])) throw new Error('partition shape');
      table.set(pair[0], pair[1]);
    }
    const pathname = decodeURIComponent(location.pathname.slice(base.pathname.length));
    const current = !pathname || pathname.endsWith('/') ? pathname + 'index.html' : pathname;
    if (!location.pathname.startsWith(base.pathname) || current !== value.document_route || (table.get(current) || 'ordinary') !== value.document_partition) throw new Error('document partition');
    initial = value.document_partition;
  } catch (_) {
    // Invalid published metadata cannot grant an instant-navigation exception.
    // Native document navigation is the conservative availability fallback;
    // independent artifact admission still rejects malformed/stale metadata.
    return () => '_self';
  }
  return url => {
    let target;
    try { target = new URL(url, location.href); } catch (_) { return '_self'; }
    if (target.origin !== base.origin || !target.pathname.startsWith(base.pathname)) return undefined;
    let route;
    try { route = decodeURIComponent(target.pathname.slice(base.pathname.length)); } catch (_) { return '_self'; }
    route = !route || route.endsWith('/') ? route + 'index.html' : route;
    return (table.get(route) || 'ordinary') === initial ? undefined : '_self';
  };
})();
