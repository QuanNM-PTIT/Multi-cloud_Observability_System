import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  Cloud,
  Copy,
  Cpu,
  Gauge,
  HardDrive,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  Network,
  PackageCheck,
  Plus,
  RefreshCcw,
  Search,
  Server,
  ShieldCheck,
  Trash2,
  UserPlus,
  X
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

type User = {
  id: string;
  username: string;
  email: string;
  full_name: string | null;
  status: string;
  grafana_user_id: string | null;
};

type Vm = {
  id: string;
  vm_name: string;
  cloud_provider: string;
  public_ip: string | null;
  private_ip: string | null;
  os_type: string;
  os_version: string | null;
  environment: string | null;
  description: string | null;
  monitoring_status: string;
  is_monitoring: boolean;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string | null;
};

type VmFormState = {
  vm_name: string;
  cloud_provider: string;
  public_ip: string;
  private_ip: string;
  os_type: string;
  os_other: string;
  environment: string;
  description: string;
};

type AgentPackage = {
  vm_id: string;
  package_id: string;
  package_name: string;
  download_url: string;
  checksum: string | null;
  file_size_bytes: number | null;
  action: string | null;
  script: string | null;
  script_token_expires_at: string | null;
  expires_in_seconds: number | null;
};

type AgentScript = {
  vm_id: string;
  action: string;
  script: string;
  script_token_expires_at: string;
  expires_in_seconds: number;
};

type AgentStatus = {
  vm_id: string;
  agent_status: string;
  agent_version: string | null;
  service_status: string | null;
  last_seen_at: string | null;
  last_heartbeat_at: string | null;
  last_error_message: string | null;
  updated_at: string | null;
};

type GrafanaEmbedPanel = {
  key: string;
  title: string;
  panel_id: number;
  iframe_url: string;
  height: number;
};

type VmDashboardPanels = {
  vm_id: string;
  host_name: string;
  dashboard_uid: string;
  panels: GrafanaEmbedPanel[];
};

type Notice = {
  type: "success" | "error" | "info";
  message: string;
};

const emptyVmForm: VmFormState = {
  vm_name: "",
  cloud_provider: "digitalocean",
  public_ip: "",
  private_ip: "",
  os_type: "Ubuntu",
  os_other: "",
  environment: "dev",
  description: ""
};

const cloudOptions = [
  { value: "aws", label: "AWS" },
  { value: "gcp", label: "Google Cloud Platform" },
  { value: "azure", label: "Microsoft Azure" },
  { value: "digitalocean", label: "DigitalOcean" },
  { value: "viettel-idc", label: "Viettel IDC" },
  { value: "openstack", label: "OpenStack" },
  { value: "private-cloud", label: "Private Cloud" },
  { value: "other", label: "Other" }
];

const osOptions = [
  "Linux",
  "Ubuntu",
  "Debian",
  "Red Hat Enterprise Linux",
  "CentOS Stream",
  "Rocky Linux",
  "AlmaLinux",
  "Amazon Linux",
  "Oracle Linux",
  "SUSE Linux Enterprise Server",
  "Windows",
  "Windows Server 2022",
  "Windows Server 2019",
  "Other"
];

const statusLabels: Record<string, string> = {
  NOT_INSTALLED: "Not installed",
  PACKAGE_GENERATED: "Package generated",
  DOWNLOADED: "Downloaded",
  INSTALLING: "Installing",
  RUNNING: "Running",
  STOPPED: "Stopped",
  ERROR: "Error",
  NO_DATA: "No data"
};

function readToken(): string | null {
  /* Read the persisted access token from local storage. */
  return localStorage.getItem("obs_token");
}

async function apiRequest<T>(path: string, options: RequestInit = {}, token?: string | null): Promise<T> {
  /* Call the backend API and normalize JSON error handling for the UI. */
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData) && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const fallback = `Request failed with status ${response.status}`;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await response.json();
      throw new Error(data.detail || fallback);
    }
    throw new Error(fallback);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function formatDate(value: string | null): string {
  /* Format an ISO timestamp for compact dashboard display. */
  if (!value) {
    return "Never";
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatBytes(value: number | null): string {
  /* Convert a byte value into a short human readable label. */
  if (!value) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function isVmInstalled(vm: Vm): boolean {
  /* Return whether uninstall actions should be available for a VM. */
  return vm.is_monitoring || vm.monitoring_status === "RUNNING";
}

function statusTone(status: string): "green" | "red" | "amber" | "gray" {
  /* Map backend monitoring states to compact visual status tones. */
  if (status === "RUNNING") {
    return "green";
  }
  if (status === "ERROR" || status === "STOPPED") {
    return "red";
  }
  if (status === "PACKAGE_GENERATED" || status === "DOWNLOADED" || status === "INSTALLING" || status === "NO_DATA") {
    return "amber";
  }
  return "gray";
}

function toPayload(form: VmFormState): Record<string, string | null> {
  /* Convert VM form state into the backend create or update payload. */
  const osType = form.os_type === "Other" ? form.os_other.trim() : form.os_type;
  return {
    vm_name: form.vm_name.trim(),
    cloud_provider: form.cloud_provider,
    public_ip: form.public_ip.trim() || null,
    private_ip: form.private_ip.trim() || null,
    os_type: osType.trim(),
    os_version: null,
    environment: form.environment.trim() || null,
    description: form.description.trim() || null
  };
}

function formatCloudProvider(provider: string): string {
  /* Convert stored cloud provider codes into readable UI labels. */
  return cloudOptions.find((option) => option.value === provider)?.label || provider;
}

function createVmFormFromVm(vm: Vm): VmFormState {
  /* Convert a VM record into form state while preserving custom OS values. */
  const knownOs = osOptions.includes(vm.os_type);
  return {
    vm_name: vm.vm_name,
    cloud_provider: cloudOptions.some((option) => option.value === vm.cloud_provider) ? vm.cloud_provider : "other",
    public_ip: vm.public_ip || "",
    private_ip: vm.private_ip || "",
    os_type: knownOs ? vm.os_type : "Other",
    os_other: knownOs ? "" : vm.os_type,
    environment: vm.environment || "",
    description: vm.description || ""
  };
}

function Button({
  children,
  variant = "primary",
  size = "md",
  type = "button",
  disabled,
  onClick
}: {
  children: ReactNode;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "md" | "sm" | "icon";
  type?: "button" | "submit";
  disabled?: boolean;
  onClick?: () => void;
}) {
  /* Render a consistent button used across dashboard actions. */
  return (
    <button className={`button button-${variant} button-${size}`} type={type} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}

function Badge({ children, tone }: { children: ReactNode; tone: "green" | "red" | "amber" | "gray" }) {
  /* Render a small status badge with a semantic tone. */
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function NoticeBar({ notice, onClose }: { notice: Notice | null; onClose: () => void }) {
  /* Render transient success and error feedback for API operations. */
  if (!notice) {
    return null;
  }
  return (
    <div className={`notice notice-${notice.type}`}>
      <span>{notice.message}</span>
      <button aria-label="Close notice" onClick={onClose}>
        <X size={16} />
      </button>
    </div>
  );
}

function AuthView({
  onAuthenticated
}: {
  onAuthenticated: (token: string, user: User) => void;
}) {
  /* Render login and registration forms for local portal accounts. */
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [form, setForm] = useState({
    username_or_email: "",
    username: "",
    email: "",
    full_name: "",
    password: ""
  });

  async function submit(event: FormEvent<HTMLFormElement>) {
    /* Submit the active authentication form to the backend. */
    event.preventDefault();
    setLoading(true);
    setNotice(null);
    try {
      if (mode === "register") {
        await apiRequest<User>("/auth/register", {
          method: "POST",
          body: JSON.stringify({
            username: form.username,
            email: form.email,
            full_name: form.full_name || null,
            password: form.password
          })
        });
      }
      const tokenResponse = await apiRequest<{ access_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username_or_email: mode === "login" ? form.username_or_email : form.username,
          password: form.password
        })
      });
      const user = await apiRequest<User>("/auth/me", {}, tokenResponse.access_token);
      localStorage.setItem("obs_token", tokenResponse.access_token);
      onAuthenticated(tokenResponse.access_token, user);
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "Authentication failed" });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-brand">
        <div className="brand-lockup">
          <div className="brand-mark">
            <Activity size={30} />
          </div>
          <div>
            <span className="eyebrow">MasterPTIT</span>
            <h1>Observability Portal</h1>
          </div>
        </div>
        <div className="signal-board" aria-hidden="true">
          <div className="signal-row">
            <span>CPU</span>
            <strong>41%</strong>
            <div className="signal-meter"><i style={{ width: "41%" }} /></div>
          </div>
          <div className="signal-row">
            <span>Memory</span>
            <strong>68%</strong>
            <div className="signal-meter"><i style={{ width: "68%" }} /></div>
          </div>
          <div className="signal-row">
            <span>Network</span>
            <strong>12.4 MB/s</strong>
            <div className="sparkline">
              <b /><b /><b /><b /><b /><b /><b />
            </div>
          </div>
        </div>
      </section>

      <section className="auth-panel">
        <NoticeBar notice={notice} onClose={() => setNotice(null)} />
        <div className="auth-tabs">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Login</button>
          <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>Register</button>
        </div>
        <form onSubmit={submit} className="form-stack">
          {mode === "login" ? (
            <label>
              Username or email
              <input
                value={form.username_or_email}
                onChange={(event) => setForm({ ...form, username_or_email: event.target.value })}
                autoComplete="username"
                required
              />
            </label>
          ) : (
            <>
              <label>
                Username
                <input
                  value={form.username}
                  onChange={(event) => setForm({ ...form, username: event.target.value })}
                  autoComplete="username"
                  minLength={3}
                  required
                />
              </label>
              <label>
                Email
                <input
                  type="email"
                  value={form.email}
                  onChange={(event) => setForm({ ...form, email: event.target.value })}
                  autoComplete="email"
                  required
                />
              </label>
              <label>
                Full name
                <input
                  value={form.full_name}
                  onChange={(event) => setForm({ ...form, full_name: event.target.value })}
                  autoComplete="name"
                />
              </label>
            </>
          )}
          <label>
            Password
            <input
              type="password"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "register" ? 8 : 1}
              required
            />
          </label>
          <Button type="submit" disabled={loading}>
            {mode === "login" ? <KeyRound size={18} /> : <UserPlus size={18} />}
            {loading ? "Processing..." : mode === "login" ? "Login" : "Create account"}
          </Button>
        </form>
      </section>
    </main>
  );
}

function StatCard({
  label,
  value,
  icon,
  helper
}: {
  label: string;
  value: string | number;
  icon: ReactNode;
  helper: string;
}) {
  /* Render a dashboard metric card with a fixed layout. */
  return (
    <article className="stat-card">
      <div className="stat-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{helper}</small>
    </article>
  );
}

function VmModal({
  initial,
  onCancel,
  onSubmit,
  saving
}: {
  initial: VmFormState;
  onCancel: () => void;
  onSubmit: (form: VmFormState) => void;
  saving: boolean;
}) {
  /* Render the VM create and edit modal form. */
  const [form, setForm] = useState(initial);

  function submit(event: FormEvent<HTMLFormElement>) {
    /* Validate and submit the VM form state. */
    event.preventDefault();
    if (form.os_type === "Other" && !form.os_other.trim()) {
      return;
    }
    onSubmit(form);
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="vm-modal-title">
        <div className="modal-header">
          <div>
            <span className="eyebrow">VM inventory</span>
            <h2 id="vm-modal-title">{initial.vm_name ? "Edit VM" : "Add VM"}</h2>
          </div>
          <Button variant="ghost" size="icon" onClick={onCancel}><X size={18} /></Button>
        </div>
        <form className="vm-form" onSubmit={submit}>
          <label>
            VM name
            <input value={form.vm_name} onChange={(event) => setForm({ ...form, vm_name: event.target.value })} required />
          </label>
          <label>
            Cloud provider
            <select value={form.cloud_provider} onChange={(event) => setForm({ ...form, cloud_provider: event.target.value })}>
              {cloudOptions.map((provider) => <option key={provider.value} value={provider.value}>{provider.label}</option>)}
            </select>
          </label>
          <label>
            Public IP
            <input value={form.public_ip} onChange={(event) => setForm({ ...form, public_ip: event.target.value })} />
          </label>
          <label>
            Private IP
            <input value={form.private_ip} onChange={(event) => setForm({ ...form, private_ip: event.target.value })} />
          </label>
          <label>
            Operating system
            <select value={form.os_type} onChange={(event) => setForm({ ...form, os_type: event.target.value })} required>
              {osOptions.map((os) => <option key={os} value={os}>{os}</option>)}
            </select>
          </label>
          {form.os_type === "Other" && (
            <label>
              OS information
              <input
                value={form.os_other}
                onChange={(event) => setForm({ ...form, os_other: event.target.value })}
                placeholder="Enter operating system"
                required
              />
            </label>
          )}
          <label>
            Environment
            <input value={form.environment} onChange={(event) => setForm({ ...form, environment: event.target.value })} />
          </label>
          <label className="wide">
            Description
            <textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
          </label>
          <div className="modal-actions">
            <Button variant="secondary" onClick={onCancel}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? "Saving..." : "Save VM"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function VmTable({
  vms,
  selectedVmId,
  onSelect,
  onEdit,
  onDelete,
  onGenerate,
  onGenerateUninstall,
  busyId
}: {
  vms: Vm[];
  selectedVmId: string | null;
  onSelect: (vm: Vm) => void;
  onEdit: (vm: Vm) => void;
  onDelete: (vm: Vm) => void;
  onGenerate: (vm: Vm) => void;
  onGenerateUninstall: (vm: Vm) => void;
  busyId: string | null;
}) {
  /* Render the VM inventory table with monitoring actions. */
  if (!vms.length) {
    return (
      <div className="empty-state">
        <Server size={34} />
        <h3>No VMs</h3>
        <p>Add a Linux VM to begin monitoring.</p>
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>VM</th>
            <th>Provider</th>
            <th>Network</th>
            <th>Status</th>
            <th>Last seen</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {vms.map((vm) => (
            <tr key={vm.id} className={selectedVmId === vm.id ? "selected-row" : ""} onClick={() => onSelect(vm)}>
              <td>
                <div className="vm-name-cell">
                  <span className="server-dot"><Server size={17} /></span>
                  <div>
                    <strong>{vm.vm_name}</strong>
                    <small>{vm.os_type}</small>
                  </div>
                </div>
              </td>
              <td>
                <span className="provider-pill"><Cloud size={14} />{formatCloudProvider(vm.cloud_provider)}</span>
              </td>
              <td>
                <div className="network-cell">
                  <span>{vm.public_ip || "No public IP"}</span>
                  <small>{vm.private_ip || "No private IP"}</small>
                </div>
              </td>
              <td>
                <Badge tone={statusTone(vm.monitoring_status)}>
                  {statusLabels[vm.monitoring_status] || vm.monitoring_status}
                </Badge>
              </td>
              <td>{formatDate(vm.last_seen_at)}</td>
              <td>
                <div className="row-actions">
                  <button title="Generate package" onClick={(event) => { event.stopPropagation(); onGenerate(vm); }} disabled={busyId === vm.id}>
                    <PackageCheck size={17} />
                  </button>
                  <button title="Generate uninstall script" onClick={(event) => { event.stopPropagation(); onGenerateUninstall(vm); }} disabled={busyId === vm.id || !isVmInstalled(vm)}>
                    <ShieldCheck size={17} />
                  </button>
                  <button title="Edit VM" onClick={(event) => { event.stopPropagation(); onEdit(vm); }} disabled={busyId === vm.id}>
                    <Gauge size={17} />
                  </button>
                  <button title="Delete VM" className="danger-icon" onClick={(event) => { event.stopPropagation(); onDelete(vm); }} disabled={busyId === vm.id}>
                    <Trash2 size={17} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GrafanaPanel({ title, iframeUrl, height }: { title: string; iframeUrl: string; height: number }) {
  /* Render one Grafana iframe panel with a portal-side loading skeleton. */
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setLoaded(false);
  }, [iframeUrl]);

  function handleLoad() {
    /* Delay the iframe reveal so Grafana's own loading badge stays hidden behind the portal loader. */
    window.setTimeout(() => setLoaded(true), 500);
  }

  return (
    <article className="grafana-panel-card">
      <div className="grafana-panel-title">
        <span>{title}</span>
      </div>
      <div className="grafana-frame-wrap" style={{ height }}>
        {!loaded && (
          <div className="grafana-loader" aria-label={`Loading ${title}`}>
            <div className="grafana-loader-grid">
              <span />
              <span />
              <span />
              <span />
            </div>
            <div className="grafana-loader-lines">
              <i />
              <i />
              <i />
            </div>
          </div>
        )}
        <iframe
          className={loaded ? "loaded" : ""}
          title={title}
          src={iframeUrl}
          width="100%"
          height="100%"
          frameBorder="0"
          loading="lazy"
          onLoad={handleLoad}
        />
      </div>
    </article>
  );
}

function VmMonitoringPage({
  vm,
  vms,
  token,
  onSelectVm
}: {
  vm: Vm | null;
  vms: Vm[];
  token: string;
  onSelectVm: (vmId: string) => void;
}) {
  /* Load and render backend-generated Grafana d-solo panels for a selected VM. */
  const [dashboard, setDashboard] = useState<VmDashboardPanels | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadPanels() {
    /* Fetch Grafana iframe panel URLs for the selected VM from the backend. */
    if (!vm) {
      setDashboard(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<VmDashboardPanels>(`/vms/${vm.id}/dashboard-panels`, {}, token);
      setDashboard(data);
    } catch (loadError) {
      setDashboard(null);
      setError(loadError instanceof Error ? loadError.message : "Could not load Grafana panels");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPanels();
  }, [vm?.id]);

  if (!vm) {
    return (
      <section className="monitoring-page">
        <div className="empty-state">
          <BarChart3 size={34} />
          <h3>No VM selected</h3>
          <p>Add or select a VM to view monitoring panels.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="monitoring-page">
      <div className="monitoring-header">
        <div>
          <span className="eyebrow">Grafana embedded panels</span>
          <h2>{vm.vm_name}</h2>
          <p>Dashboard UID: {dashboard?.dashboard_uid || "masterptit-vm-observability"}</p>
        </div>
        <div className="monitoring-meta">
          <label className="monitoring-vm-select">
            <span>VM</span>
            <select value={vm.id} onChange={(event) => onSelectVm(event.target.value)}>
              {vms.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.vm_name}
                </option>
              ))}
            </select>
          </label>
          <Badge tone={statusTone(vm.monitoring_status)}>
            {statusLabels[vm.monitoring_status] || vm.monitoring_status}
          </Badge>
          <Button variant="secondary" size="sm" onClick={loadPanels}>
            <RefreshCcw size={16} />Refresh panels
          </Button>
        </div>
      </div>

      {loading && <div className="loading-line">Loading Grafana panels...</div>}
      {error && <NoticeBar notice={{ type: "error", message: error }} onClose={() => setError(null)} />}
      {!loading && !error && dashboard && (
        <div className="grafana-grid">
          {dashboard.panels.map((panel) => (
            <GrafanaPanel
              key={panel.key}
              title={panel.title}
              iframeUrl={panel.iframe_url}
              height={panel.height}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function AppShell({
  user,
  token,
  onLogout
}: {
  user: User;
  token: string;
  onLogout: () => void;
}) {
  /* Render the authenticated portal shell and coordinate dashboard API state. */
  const [vms, setVms] = useState<Vm[]>([]);
  const [selectedVmId, setSelectedVmId] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [latestScript, setLatestScript] = useState<(AgentScript & { package_name?: string; file_size_bytes?: number | null }) | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "running" | "attention">("all");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [page, setPage] = useState<"dashboard" | "grafana">("dashboard");
  const [modalState, setModalState] = useState<{ vm?: Vm; form: VmFormState } | null>(null);

  const selectedVm = useMemo(() => vms.find((vm) => vm.id === selectedVmId) || vms[0] || null, [selectedVmId, vms]);

  const filteredVms = useMemo(() => {
    /* Apply search and status filters to VM inventory rows. */
    return vms.filter((vm) => {
      const text = `${vm.vm_name} ${vm.cloud_provider} ${formatCloudProvider(vm.cloud_provider)} ${vm.os_type} ${vm.environment || ""} ${vm.public_ip || ""}`.toLowerCase();
      const matchesQuery = text.includes(query.toLowerCase());
      const matchesFilter =
        filter === "all" ||
        (filter === "running" && vm.monitoring_status === "RUNNING") ||
        (filter === "attention" && ["ERROR", "STOPPED", "NO_DATA", "NOT_INSTALLED"].includes(vm.monitoring_status));
      return matchesQuery && matchesFilter;
    });
  }, [filter, query, vms]);

  const stats = useMemo(() => {
    /* Calculate top-level operational counters from VM records. */
    const running = vms.filter((vm) => vm.monitoring_status === "RUNNING").length;
    const attention = vms.filter((vm) => ["ERROR", "STOPPED", "NO_DATA"].includes(vm.monitoring_status)).length;
    const packages = vms.filter((vm) => ["PACKAGE_GENERATED", "DOWNLOADED"].includes(vm.monitoring_status)).length;
    return { total: vms.length, running, attention, packages };
  }, [vms]);

  async function loadVms() {
    /* Load VM inventory from the backend and select a stable active VM. */
    setLoading(true);
    try {
      const data = await apiRequest<{ items: Vm[] }>("/vms", {}, token);
      setVms(data.items);
      setSelectedVmId((current) => current || data.items[0]?.id || null);
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "Could not load VMs" });
    } finally {
      setLoading(false);
    }
  }

  async function loadAgentStatus(vmId: string) {
    /* Load latest agent status for the currently selected VM. */
    try {
      const data = await apiRequest<AgentStatus>(`/vms/${vmId}/agent-status`, {}, token);
      setAgentStatus(data);
    } catch {
      setAgentStatus(null);
    }
  }

  async function saveVm(form: VmFormState) {
    /* Create or update a VM and refresh the inventory table. */
    setSaving(true);
    try {
      if (modalState?.vm) {
        await apiRequest<Vm>(`/vms/${modalState.vm.id}`, {
          method: "PUT",
          body: JSON.stringify(toPayload(form))
        }, token);
        setNotice({ type: "success", message: "VM updated" });
      } else {
        await apiRequest<Vm>("/vms", {
          method: "POST",
          body: JSON.stringify(toPayload(form))
        }, token);
        setNotice({ type: "success", message: "VM added" });
      }
      setModalState(null);
      await loadVms();
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "Could not save VM" });
    } finally {
      setSaving(false);
    }
  }

  async function deleteVm(vm: Vm) {
    /* Delete a VM after confirmation and refresh the inventory. */
    if (!window.confirm(`Delete ${vm.vm_name}?`)) {
      return;
    }
    setBusyId(vm.id);
    try {
      await apiRequest<void>(`/vms/${vm.id}`, { method: "DELETE" }, token);
      setNotice({ type: "success", message: "VM deleted" });
      setSelectedVmId(null);
      await loadVms();
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "Could not delete VM" });
    } finally {
      setBusyId(null);
    }
  }

  async function generatePackage(vm: Vm) {
    /* Generate a package and VM-side install script for the selected VM. */
    setBusyId(vm.id);
    try {
      const data = await apiRequest<AgentPackage>(`/vms/${vm.id}/agent-package`, { method: "POST" }, token);
      if (data.script && data.script_token_expires_at) {
        setLatestScript({
          vm_id: data.vm_id,
          action: data.action || "INSTALL",
          script: data.script,
          script_token_expires_at: data.script_token_expires_at,
          expires_in_seconds: data.expires_in_seconds || 900,
          package_name: data.package_name,
          file_size_bytes: data.file_size_bytes,
        });
      }
      setNotice({ type: "success", message: `Generated install script for ${vm.vm_name}` });
      await loadVms();
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "Could not generate package" });
    } finally {
      setBusyId(null);
    }
  }

  async function generateUninstallScript(vm: Vm) {
    /* Generate a VM-side uninstall script for an installed agent. */
    setBusyId(vm.id);
    try {
      const data = await apiRequest<AgentScript>(`/vms/${vm.id}/agent-uninstall-script`, { method: "POST" }, token);
      setLatestScript(data);
      setNotice({ type: "success", message: `Generated uninstall script for ${vm.vm_name}` });
    } catch (error) {
      setNotice({ type: "error", message: error instanceof Error ? error.message : "Could not generate uninstall script" });
    } finally {
      setBusyId(null);
    }
  }

  async function copyLatestScript() {
    /* Copy the latest generated VM-side script to the clipboard. */
    if (!latestScript?.script) {
      return;
    }
    await navigator.clipboard.writeText(latestScript.script);
    setNotice({ type: "success", message: "Script copied to clipboard" });
  }

  function editVm(vm: Vm) {
    /* Open the VM modal with fields populated from an existing VM. */
    setModalState({ vm, form: createVmFormFromVm(vm) });
  }

  useEffect(() => {
    loadVms();
  }, []);

  useEffect(() => {
    if (selectedVm?.id) {
      loadAgentStatus(selectedVm.id);
    } else {
      setAgentStatus(null);
    }
  }, [selectedVm?.id]);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <div className="brand-mark compact"><Activity size={24} /></div>
          <div>
            <strong>MasterPTIT</strong>
            <span>Observability</span>
          </div>
        </div>
        <nav>
          <button className={page === "dashboard" ? "active" : ""} onClick={() => setPage("dashboard")}><LayoutDashboard size={18} />Dashboard</button>
          <button className={page === "grafana" ? "active" : ""} onClick={() => setPage("grafana")}><BarChart3 size={18} />Monitoring</button>
        </nav>
        <div className="sidebar-footer">
          <div className="user-chip">
            <span>{user.username.slice(0, 1).toUpperCase()}</span>
            <div>
              <strong>{user.full_name || user.username}</strong>
              <small>{user.email}</small>
            </div>
          </div>
          <Button variant="secondary" onClick={onLogout}><LogOut size={17} />Logout</Button>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(!sidebarOpen)}><Menu size={20} /></Button>
          <div>
            <span className="eyebrow">Multi-cloud VM monitoring</span>
            <h1>{page === "grafana" ? "VM Monitoring" : "Operations Dashboard"}</h1>
          </div>
          <div className="topbar-actions">
            <Button variant="secondary" onClick={loadVms}><RefreshCcw size={17} />Refresh</Button>
            <Button onClick={() => setModalState({ form: emptyVmForm })}><Plus size={18} />Add VM</Button>
          </div>
        </header>

        <NoticeBar notice={notice} onClose={() => setNotice(null)} />

        {page === "dashboard" ? (
          <>
            <section className="stats-grid">
              <StatCard label="Total VMs" value={stats.total} helper="Registered inventory" icon={<Server size={22} />} />
              <StatCard label="Running" value={stats.running} helper="Healthy agents" icon={<CheckCircle2 size={22} />} />
              <StatCard label="Needs attention" value={stats.attention} helper="Stopped, error, no data" icon={<AlertTriangle size={22} />} />
              <StatCard label="Packages" value={stats.packages} helper="Generated or downloaded" icon={<PackageCheck size={22} />} />
            </section>

            <section className="workspace-grid">
              <article className="inventory-panel">
                <div className="panel-header">
                  <div>
                    <span className="eyebrow">Inventory</span>
                    <h2>Virtual Machines</h2>
                  </div>
                  <div className="search-box">
                    <Search size={17} />
                    <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search VM, provider, IP" />
                  </div>
                </div>
                <div className="segmented">
                  <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>All</button>
                  <button className={filter === "running" ? "active" : ""} onClick={() => setFilter("running")}>Running</button>
                  <button className={filter === "attention" ? "active" : ""} onClick={() => setFilter("attention")}>Attention</button>
                </div>
                {loading ? <div className="loading-line">Loading inventory...</div> : (
                  <VmTable
                    vms={filteredVms}
                    selectedVmId={selectedVm?.id || null}
                    onSelect={(vm) => setSelectedVmId(vm.id)}
                    onEdit={editVm}
                    onDelete={deleteVm}
                    onGenerate={generatePackage}
                    onGenerateUninstall={generateUninstallScript}
                    busyId={busyId}
                  />
                )}
              </article>

              <aside className="detail-panel">
                <div className="panel-header compact-header">
                  <div>
                    <span className="eyebrow">Selected VM</span>
                    <h2>{selectedVm?.vm_name || "No VM selected"}</h2>
                  </div>
                  <ChevronDown size={18} />
                </div>
                {selectedVm ? (
                  <>
                    <div className="status-card">
                      <Badge tone={statusTone(selectedVm.monitoring_status)}>
                        {statusLabels[selectedVm.monitoring_status] || selectedVm.monitoring_status}
                      </Badge>
                      <strong>{formatCloudProvider(selectedVm.cloud_provider)}</strong>
                      <span>{selectedVm.environment || "default"}</span>
                    </div>
                    <div className="metric-stack">
                      <div><Cpu size={18} /><span>OS</span><strong>{selectedVm.os_type}</strong></div>
                      <div><Network size={18} /><span>Public IP</span><strong>{selectedVm.public_ip || "N/A"}</strong></div>
                      <div><HardDrive size={18} /><span>Last seen</span><strong>{formatDate(selectedVm.last_seen_at)}</strong></div>
                    </div>
                    <div className="agent-panel">
                      <div>
                        <span className="eyebrow">Agent status</span>
                        <h3>{agentStatus?.agent_status || "UNKNOWN"}</h3>
                      </div>
                      <small>Heartbeat: {formatDate(agentStatus?.last_heartbeat_at || null)}</small>
                      <small>Service: {agentStatus?.service_status || "unknown"}</small>
                    </div>
                    {latestScript?.vm_id === selectedVm.id && (
                      <div className="script-card">
                        <div className="script-card-header">
                          <div>
                            <span className="eyebrow">{latestScript.action === "UNINSTALL" ? "Uninstall script" : "Install script"}</span>
                            <strong>{latestScript.package_name || "VM-side command"}</strong>
                            <small>
                              Expires at {formatDate(latestScript.script_token_expires_at)}
                              {latestScript.file_size_bytes ? ` / ${formatBytes(latestScript.file_size_bytes)}` : ""}
                            </small>
                          </div>
                          <Button variant="secondary" size="sm" onClick={copyLatestScript}>
                            <Copy size={16} />Copy
                          </Button>
                        </div>
                        <textarea readOnly value={latestScript.script} aria-label="Generated one-line VM command" />
                      </div>
                    )}
                    <div className="detail-actions">
                      <Button onClick={() => generatePackage(selectedVm)} disabled={busyId === selectedVm.id}>
                        <PackageCheck size={17} />Generate install script
                      </Button>
                      <Button variant="secondary" onClick={() => generateUninstallScript(selectedVm)} disabled={busyId === selectedVm.id || !isVmInstalled(selectedVm)}>
                        <ShieldCheck size={17} />Generate uninstall script
                      </Button>
                      <Button variant="secondary" onClick={() => setPage("grafana")}>
                        <BarChart3 size={17} />Open monitoring
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="empty-state side-empty">
                    <Activity size={32} />
                    <h3>No selection</h3>
                  </div>
                )}
              </aside>
            </section>
          </>
        ) : (
          <VmMonitoringPage
            vm={selectedVm}
            vms={vms}
            token={token}
            onSelectVm={(vmId) => setSelectedVmId(vmId)}
          />
        )}
      </main>

      {modalState && (
        <VmModal
          initial={modalState.form}
          saving={saving}
          onCancel={() => setModalState(null)}
          onSubmit={saveVm}
        />
      )}
    </div>
  );
}

export default function App() {
  /* Coordinate authentication state between local storage and the application shell. */
  const [token, setToken] = useState<string | null>(() => readToken());
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(token));

  useEffect(() => {
    async function loadCurrentUser() {
      /* Restore the current user when a saved token exists. */
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const data = await apiRequest<User>("/auth/me", {}, token);
        setUser(data);
      } catch {
        localStorage.removeItem("obs_token");
        setToken(null);
      } finally {
        setLoading(false);
      }
    }
    loadCurrentUser();
  }, [token]);

  if (loading) {
    return (
      <div className="boot-screen">
        <div className="brand-mark"><Activity size={28} /></div>
        <span>Loading portal...</span>
      </div>
    );
  }

  if (!token || !user) {
    return <AuthView onAuthenticated={(nextToken, nextUser) => {
      setToken(nextToken);
      setUser(nextUser);
    }} />;
  }

  return <AppShell user={user} token={token} onLogout={() => {
    localStorage.removeItem("obs_token");
    setToken(null);
    setUser(null);
  }} />;
}
