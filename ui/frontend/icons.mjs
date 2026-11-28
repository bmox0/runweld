export const sprite = `<svg width="0" height="0" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" class="rw-sprite">
<symbol id="r-flow" viewBox="0 0 20 20"><path d="M5 5v10m4-5h5m-9 0h2"/><circle cx="5" cy="4" r="1.6"/><circle cx="5" cy="16" r="1.6"/><circle cx="15" cy="10" r="1.6"/></symbol>
<symbol id="r-folder" viewBox="0 0 20 20"><path d="M2.5 5h6l2 2h7v8.5h-15z"/></symbol>
<symbol id="r-arrow" viewBox="0 0 20 20"><path d="M4 10h12m-5-5 5 5-5 5"/></symbol>
<symbol id="r-left" viewBox="0 0 20 20"><path d="M16 10H4m5-5-5 5 5 5"/></symbol>
<symbol id="r-branch" viewBox="0 0 20 20"><path d="M6 7.5v5m0 0C6 7.5 14 9 14 6"/><circle cx="6" cy="5.5" r="2"/><circle cx="6" cy="14.5" r="2"/><circle cx="14" cy="4.5" r="2"/></symbol>
<symbol id="r-tree" viewBox="0 0 20 20"><path d="M5 5h10v10H5zm4 0V3m2 14v-2M3 8h2m10 4h2"/></symbol>
<symbol id="r-file" viewBox="0 0 20 20"><path d="M5 2.5h6l4 4v11H5zm6 0v4h4M7.5 10h5m-5 3h5"/></symbol>
<symbol id="r-photo" viewBox="0 0 20 20"><rect x="3" y="4" width="14" height="12" rx="2"/><path d="m4 14 4-4 2 2 2.5-2.5L16 13"/><circle cx="12.5" cy="7" r=".5"/></symbol>
<symbol id="r-check" viewBox="0 0 20 20"><path d="m4.5 10 3.4 3.3 7.6-7.6"/></symbol>
<symbol id="r-clock" viewBox="0 0 20 20"><circle cx="10" cy="10" r="6.5"/><path d="M10 6v4l2.8 1.6"/></symbol>
<symbol id="r-alert" viewBox="0 0 20 20"><circle cx="10" cy="10" r="7"/><path d="M10 6v4m0 3.5v.2"/></symbol>
<symbol id="r-user" viewBox="0 0 20 20"><circle cx="10" cy="6" r="2.6"/><path d="M4.5 16v-1c0-2.3 2.5-4 5.5-4s5.5 1.7 5.5 4v1"/></symbol>
<symbol id="r-code" viewBox="0 0 20 20"><path d="m6 6-4 4 4 4m8-8 4 4-4 4"/></symbol>
</svg>`;

export const icon = (name, small = false) => `<svg class="ri${small ? " s" : ""}" aria-hidden="true"><use href="#r-${name}"/></svg>`;
