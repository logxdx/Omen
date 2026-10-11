// One React component per Omen UI component type (props typed from generated/components.ts).

import { useMemo, useState, type ReactNode } from "react";
import type {
  CardProps, ChartProps, ChoiceProps, ComponentProps, ComponentType, DelegationProps, DiffProps, DownloadProps,
  FileDeleteProps, FileListProps, FileProps, FileWriteProps, GrepProps, LinkPreviewProps, MemorySavedProps,
  SearchResultsProps, SkillLoadedProps, TableProps, UIPayload, VideoResultsProps, WeatherProps,
} from "../generated/components";

type Renderers = { [K in ComponentType]: (props: ComponentProps[K]) => ReactNode };

const host = (url: string) => {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
};

function Weather(p: WeatherProps) {
  return (
    <div className="card weather">
      <div className="card-title">☁ {p.place}</div>
      <div className="weather-now">
        <span className="temp">{p.temp_c}°C</span>
        <span>{p.condition}</span>
        {p.feels_like_c != null && <span className="muted">feels like {p.feels_like_c}°C</span>}
      </div>
      <div className="muted">
        {[p.humidity != null && `humidity ${p.humidity}%`, p.wind_kmph != null && `wind ${p.wind_kmph} km/h`].filter(Boolean).join(" · ")}
      </div>
      {!!p.forecast?.length && (
        <div className="forecast">
          {p.forecast.map((d) => (
            <div key={d.date} className="forecast-day">
              <div className="muted">{new Date(d.date).toLocaleDateString(undefined, { weekday: "short" })}</div>
              <div>{d.min_c}–{d.max_c}°</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LinkPreview(p: LinkPreviewProps) {
  return (
    <a className="card link" href={p.url} target="_blank" rel="noreferrer">
      <div className="card-title">🔗 {p.title}</div>
      {p.description && <div className="muted">{p.description}</div>}
      <div className="url">{p.site ?? host(p.url)}</div>
    </a>
  );
}

function SearchResults(p: SearchResultsProps) {
  return (
    <div className="card">
      <div className="card-title">🔎 {p.query}</div>
      <ol className="results">
        {(p.results ?? []).map((r) => (
          <li key={r.link}>
            <a href={r.link} target="_blank" rel="noreferrer">{r.title}</a>
            <div className="url">{host(r.link)}</div>
            {r.snippet && <div className="muted snippet">{r.snippet}</div>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function VideoResults(p: VideoResultsProps) {
  return (
    <div className="card">
      <div className="card-title">▶ {p.query}</div>
      <ol className="results">
        {(p.results ?? []).map((v, i) => (
          <li key={v.url ?? i}>
            {v.url ? <a href={v.url} target="_blank" rel="noreferrer">{v.title}</a> : v.title}
            <span className="muted"> · {v.channel} {v.duration}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

const Line = ({ icon, children }: { icon: string; children: ReactNode }) => (
  <div className="line"><span className="icon">{icon}</span>{children}</div>
);

const File = (p: FileProps) => (
  <Line icon="📄"><b>{p.path}</b> <span className="muted">lines {p.start}–{p.end} of {p.total_lines}</span></Line>
);
const FileList = (p: FileListProps) => (
  <div className="card">
    <div className="card-title">📁 {p.path}/</div>
    <ul className="files">{(p.entries ?? []).map((e) => <li key={e}>{e}</li>)}</ul>
  </div>
);
const FileWrite = (p: FileWriteProps) => <Line icon="✎"><b>{p.path}</b> {p.created ? "created" : "saved"}</Line>;
const FileDelete = (p: FileDeleteProps) => <Line icon="🗑"><b>{p.path}</b> deleted</Line>;

function Diff(p: DiffProps) {
  return (
    <div className="card diff">
      <div className="card-title">✎ {p.path}</div>
      <pre>
        {p.before.split("\n").map((l, i) => <div key={`b${i}`} className="del">- {l}</div>)}
        {p.after.split("\n").map((l, i) => <div key={`a${i}`} className="add">+ {l}</div>)}
      </pre>
    </div>
  );
}

const Grep = (p: GrepProps) => (
  <div className="card">
    <div className="card-title">🔍 {p.pattern}</div>
    {p.matches?.length ? <pre className="matches">{p.matches.join("\n")}</pre> : <div className="muted">no matches</div>}
  </div>
);

const Choice = (p: ChoiceProps) => (
  <Line icon="?">{p.question} {p.answer ? <b>→ {p.answer}</b> : <span className="muted">[{p.options?.join(" / ")}]</span>}</Line>
);
const Delegation = (p: DelegationProps) => (
  <Line icon="↳"><b className="accent">{p.persona}</b>{p.shared_context ? " (with context)" : ""}: <span className="muted">{p.task}</span></Line>
);
const MemorySaved = (p: MemorySavedProps) => <Line icon="✓">remembered: {p.fact}</Line>;
const SkillLoaded = (p: SkillLoadedProps) => <Line icon="⚙"><span className="muted">skill: {p.skill}</span></Line>;
const Download = (p: DownloadProps) => <Line icon="⬇">{p.kind} downloaded <span className="muted">{p.url}</span></Line>;

function Table(p: TableProps) {
  const [sort, setSort] = useState<{ col: number; asc: boolean } | null>(null);
  const rows = useMemo(() => {
    if (!sort) return p.rows;
    const num = (s: string) => Number(s.replace(/[^0-9.-]/g, ""));
    return [...p.rows].sort((a, b) => {
      const [x, y] = [a[sort.col] ?? "", b[sort.col] ?? ""];
      const cmp = !isNaN(num(x)) && !isNaN(num(y)) && x.trim() && y.trim() ? num(x) - num(y) : x.localeCompare(y);
      return sort.asc ? cmp : -cmp;
    });
  }, [p.rows, sort]);
  return (
    <div className="card table">
      {p.title && <div className="card-title">{p.title}</div>}
      <table>
        <thead>
          <tr>
            {p.columns.map((c, i) => (
              <th key={c} onClick={() => setSort({ col: i, asc: sort?.col === i ? !sort.asc : true })}>
                {c}{sort?.col === i ? (sort.asc ? " ▲" : " ▼") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function Chart(p: ChartProps) {
  const values = p.values ?? [];
  const labels = p.labels ?? [];
  const max = Math.max(1, ...values.map(Math.abs));
  const [w, h, pad] = [520, 220, 32];
  const step = (w - pad * 2) / Math.max(values.length, 1);
  const y = (v: number) => h - pad - ((h - pad * 2) * v) / max;
  return (
    <div className="card chart">
      <div className="card-title">📊 {p.title ?? "chart"}</div>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={p.title ?? "chart"}>
        <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} className="axis" />
        {p.kind === "line" ? (
          <polyline
            className="series-line"
            points={values.map((v, i) => `${pad + step * i + step / 2},${y(v)}`).join(" ")}
          />
        ) : (
          values.map((v, i) => (
            <rect key={i} className="bar" x={pad + step * i + step * 0.15} width={step * 0.7} y={y(v)} height={h - pad - y(v)}>
              <title>{`${labels[i]}: ${v}`}</title>
            </rect>
          ))
        )}
        {values.map((v, i) => (
          <g key={`t${i}`}>
            <text x={pad + step * i + step / 2} y={h - pad + 16} className="tick">{labels[i]}</text>
            <text x={pad + step * i + step / 2} y={y(v) - 6} className="value">{v.toLocaleString()}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function Card(p: CardProps) {
  return (
    <div className="card">
      <div className="card-title">{p.title}</div>
      <div>{p.body}</div>
      {p.url && <a href={p.url} target="_blank" rel="noreferrer" className="url">{p.url}</a>}
    </div>
  );
}

const RENDERERS: Renderers = {
  weather: Weather, link_preview: LinkPreview, search_results: SearchResults, video_results: VideoResults,
  file: File, file_list: FileList, file_write: FileWrite, file_delete: FileDelete, diff: Diff, grep: Grep,
  choice: Choice, delegation: Delegation, memory_saved: MemorySaved, skill_loaded: SkillLoaded, download: Download,
  table: Table, chart: Chart, card: Card,
};

export const SUPPORTED = Object.keys(RENDERERS);

/** Render a UIPayload; unknown or invalid components fall back to their text. */
export function Component({ payload }: { payload: UIPayload }) {
  const render = RENDERERS[payload.type as ComponentType] as ((p: unknown) => ReactNode) | undefined;
  if (!render || payload.valid === false) {
    return payload.text ? <div className="card fallback">{payload.text}</div> : null;
  }
  return <div className={`component component-${payload.type}`}>{render(payload.props)}</div>;
}
