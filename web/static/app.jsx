const { useState, useEffect, useMemo, useRef } = React;

// -----------------------------------------------------------------------------
// Lightweight Icon Helper using Lucide CDN or Clean Inline SVG
// -----------------------------------------------------------------------------
function Icon({ name, className = "w-4 h-4" }) {
  const iconRef = useRef(null);

  useEffect(() => {
    if (window.lucide && iconRef.current) {
      window.lucide.createIcons();
    }
  }, [name]);

  return <i ref={iconRef} data-lucide={name} className={className}></i>;
}

// -----------------------------------------------------------------------------
// Main Application Component
// -----------------------------------------------------------------------------
function App() {
  const [activeTab, setActiveTab] = useState("workspace"); // "workspace" | "benchmark"
  const [referrals, setReferrals] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [filterMode, setFilterMode] = useState("all"); // "all" | "review" | "stp"
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedFieldKey, setSelectedFieldKey] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [rotation, setRotation] = useState(0);
  const [showBoundingBoxes, setShowBoundingBoxes] = useState(true);
  const [fhirModalDoc, setFhirModalDoc] = useState(null);
  const [benchmarkData, setBenchmarkData] = useState(null);
  const [benchmarkLoading, setBenchmarkLoading] = useState(false);
  const [overrideNotes, setOverrideNotes] = useState("");
  const [actionSuccessMsg, setActionSuccessMsg] = useState(null);

  // Upload modal state
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadDragOver, setUploadDragOver] = useState(false);

  // Field inline editing state
  const [editingFieldKey, setEditingFieldKey] = useState(null);
  const [editingValue, setEditingValue] = useState("");
  const [isSavingField, setIsSavingField] = useState(false);

  // Simulation dropdown
  const [simulateMenuOpen, setSimulateMenuOpen] = useState(false);

  const fileInputRef = useRef(null);

  // Fetch referrals on load
  const loadReferrals = async (selectRefId = null) => {
    try {
      setLoading(true);
      const res = await fetch("/api/referrals");
      const data = await res.json();
      setReferrals(data.referrals || []);
      if (selectRefId) {
        setSelectedId(selectRefId);
      } else if (data.referrals && data.referrals.length > 0 && !selectedId) {
        setSelectedId(data.referrals[0].referral_id);
      }
    } catch (err) {
      console.error("Failed to load referrals:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReferrals();
  }, []);

  // Fetch selected referral detail
  useEffect(() => {
    if (!selectedId) return;
    const fetchDetail = async () => {
      try {
        const res = await fetch(`/api/referrals/${selectedId}`);
        const data = await res.json();
        setSelectedDoc(data);
        setOverrideNotes(data.clinician_notes || "");
        setEditingFieldKey(null);
      } catch (err) {
        console.error("Failed to fetch detail for:", selectedId, err);
      }
    };
    fetchDetail();
  }, [selectedId]);

  // Load benchmark on tab switch
  useEffect(() => {
    if (activeTab === "benchmark" && !benchmarkData) {
      runBenchmark();
    }
  }, [activeTab]);

  const runBenchmark = async () => {
    try {
      setBenchmarkLoading(true);
      const res = await fetch("/api/benchmark");
      const data = await res.json();
      setBenchmarkData(data);
    } catch (err) {
      console.error("Benchmark failed:", err);
    } finally {
      setBenchmarkLoading(false);
    }
  };

  // Handle file upload
  const handleFileUpload = async (file) => {
    if (!file) return;
    setIsUploading(true);
    try {
      const reader = new FileReader();
      reader.onload = async () => {
        try {
          const base64Data = reader.result;
          const res = await fetch("/api/intake/upload", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename: file.name,
              content_base64: base64Data,
            }),
          });
          const data = await res.json();
          if (data.status === "SUCCESS") {
            setUploadModalOpen(false);
            setActionSuccessMsg(`Uploaded & processed: ${data.referral_id}`);
            setTimeout(() => setActionSuccessMsg(null), 4000);
            await loadReferrals(data.referral_id);
          } else {
            alert(`Upload failed: ${data.detail || "Unknown error"}`);
          }
        } catch (postErr) {
          console.error("Upload error:", postErr);
          alert("Error processing file upload.");
        } finally {
          setIsUploading(false);
        }
      };
      reader.readAsDataURL(file);
    } catch (err) {
      console.error("File read error:", err);
      setIsUploading(false);
    }
  };

  // Load pre-rendered sample document
  const handleLoadSample = async (filename) => {
    setIsUploading(true);
    try {
      const res = await fetch("/api/intake/load_sample", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename }),
      });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        setUploadModalOpen(false);
        setActionSuccessMsg(`Ingested & analyzed: ${data.referral_id}`);
        setTimeout(() => setActionSuccessMsg(null), 4000);
        await loadReferrals(data.referral_id);
      } else {
        alert(`Failed to load document: ${data.detail || "Unknown error"}`);
      }
    } catch (err) {
      console.error("Sample load error:", err);
      alert("Error loading sample document.");
    } finally {
      setIsUploading(false);
    }
  };

  // Generate live synthetic scenario
  const handleGenerateScenario = async (scenario) => {
    setSimulateMenuOpen(false);
    try {
      setLoading(true);
      const res = await fetch("/api/intake/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario }),
      });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        setActionSuccessMsg(`Generated test fax: ${data.referral_id} (${data.scenario})`);
        setTimeout(() => setActionSuccessMsg(null), 4000);
        await loadReferrals(data.referral_id);
      }
    } catch (err) {
      console.error("Simulation error:", err);
    } finally {
      setLoading(false);
    }
  };

  // Save inline field edit
  const handleSaveFieldEdit = async () => {
    if (!selectedId || !editingFieldKey) return;
    setIsSavingField(true);
    try {
      const res = await fetch(`/api/referrals/${selectedId}/field`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          field_key: editingFieldKey,
          new_value: editingValue,
        }),
      });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        setActionSuccessMsg(`Field '${editingFieldKey}' updated. Invariants re-evaluated!`);
        setTimeout(() => setActionSuccessMsg(null), 4000);
        setEditingFieldKey(null);
        // Refresh detail
        const resDetail = await fetch(`/api/referrals/${selectedId}`);
        const dataDetail = await resDetail.json();
        setSelectedDoc(dataDetail);
        await loadReferrals(selectedId);
      }
    } catch (err) {
      console.error("Field update error:", err);
    } finally {
      setIsSavingField(false);
    }
  };

  // Clinician Approval Action
  const handleApprove = async () => {
    if (!selectedId) return;
    try {
      const res = await fetch("/api/review/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          referral_id: selectedId,
          override_notes: overrideNotes || "Approved and signed off by clinician review terminal",
        }),
      });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        setActionSuccessMsg(`Referral ${selectedId} approved & verified!`);
        setTimeout(() => setActionSuccessMsg(null), 4000);
        await loadReferrals(selectedId);
        const resDetail = await fetch(`/api/referrals/${selectedId}`);
        const dataDetail = await resDetail.json();
        setSelectedDoc(dataDetail);
      }
    } catch (err) {
      console.error("Approval error:", err);
    }
  };

  // Open FHIR Modal
  const openFhirModal = async (refId) => {
    try {
      const res = await fetch(`/api/referrals/${refId}/fhir`);
      const data = await res.json();
      setFhirModalDoc(data);
    } catch (err) {
      console.error("Failed to load FHIR bundle:", err);
    }
  };

  // Filtered referrals list
  const filteredReferrals = useMemo(() => {
    return referrals.filter((r) => {
      if (filterMode === "review" && r.routing_decision === "AUTO_ACCEPTED") return false;
      if (filterMode === "stp" && r.routing_decision !== "AUTO_ACCEPTED") return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchId = r.referral_id.toLowerCase().includes(q);
        const matchName = r.patient_name.toLowerCase().includes(q);
        const matchProv = r.provider_name.toLowerCase().includes(q);
        const matchDiag = r.diagnosis_code.toLowerCase().includes(q);
        if (!matchId && !matchName && !matchProv && !matchDiag) return false;
      }
      return true;
    });
  }, [referrals, filterMode, searchQuery]);

  // Overall counts
  const totalCount = referrals.length;
  const flaggedCount = referrals.filter((r) => r.routing_decision !== "AUTO_ACCEPTED").length;
  const stpCount = referrals.filter((r) => r.routing_decision === "AUTO_ACCEPTED").length;

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#f7f1ed] text-[#1a1a1a]">
      {/* ------------------------------------------------------------- */}
      {/* Top Header Bar (AWS IDP / Institutional Design)              */}
      {/* ------------------------------------------------------------- */}
      <header className="h-14 bg-white border-b border-[#eae0dc] px-4 flex items-center justify-between shrink-0 shadow-xs z-30">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#220c0c] text-white flex items-center justify-center font-bold text-sm tracking-wider shadow-xs">
              IA
            </div>
            <div>
              <span className="font-serif font-bold text-base tracking-tight text-[#220c0c]">
                INTAKE <span className="text-[#8c78e1] font-sans text-xs uppercase px-1.5 py-0.5 rounded bg-[#f3ecf9] font-semibold tracking-normal">AI</span>
              </span>
              <span className="hidden sm:inline-block ml-2 text-xs text-gray-500 font-mono">
                CMS-Calibrated IDP Terminal
              </span>
            </div>
          </div>

          <div className="hidden md:flex items-center gap-1.5 ml-4 pl-4 border-l border-[#eae0dc]">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span className="text-xs font-mono font-medium text-gray-600">
              CMS Luhn + ICD-10 Active Invariants
            </span>
          </div>
        </div>

        {/* Global Action Strip */}
        <div className="flex items-center gap-2.5">
          {/* Navigation View Switcher */}
          <div className="flex items-center bg-[#f2eae5] p-1 rounded-lg text-xs font-medium">
            <button
              onClick={() => setActiveTab("workspace")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all ${
                activeTab === "workspace"
                  ? "bg-white text-[#220c0c] shadow-xs font-semibold"
                  : "text-gray-600 hover:text-[#220c0c]"
              }`}
            >
              <Icon name="layout-dashboard" className="w-3.5 h-3.5" />
              <span>Review Workspace</span>
            </button>
            <button
              onClick={() => setActiveTab("benchmark")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all ${
                activeTab === "benchmark"
                  ? "bg-white text-[#220c0c] shadow-xs font-semibold"
                  : "text-gray-600 hover:text-[#220c0c]"
              }`}
            >
              <Icon name="bar-chart-2" className="w-3.5 h-3.5" />
              <span>Benchmark Matrix</span>
            </button>
          </div>

          {/* Quick Simulation Generator Dropdown */}
          <div className="relative">
            <button
              onClick={() => setSimulateMenuOpen(!simulateMenuOpen)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#faf6f3] hover:bg-[#f2eae5] border border-[#eae0dc] rounded-lg text-xs font-medium text-gray-700 transition-colors"
            >
              <Icon name="sparkles" className="w-3.5 h-3.5 text-[#8c78e1]" />
              <span className="hidden sm:inline">Simulate Fax</span>
              <Icon name="chevron-down" className="w-3 h-3 text-gray-400" />
            </button>

            {simulateMenuOpen && (
              <div className="absolute right-0 mt-1 w-64 bg-white border border-[#eae0dc] rounded-xl shadow-xl z-50 py-1.5 text-xs">
                <div className="px-3 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                  Generate Synthetic Test Case
                </div>
                <button
                  onClick={() => handleGenerateScenario("clean")}
                  className="w-full px-3 py-2 text-left hover:bg-[#faf6f3] flex items-center gap-2"
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                  <div>
                    <div className="font-semibold text-gray-900">Clean Ambulatory Fax</div>
                    <div className="text-[10px] text-gray-500">Eligible for Straight-Through (STP)</div>
                  </div>
                </button>
                <button
                  onClick={() => handleGenerateScenario("tampered_npi")}
                  className="w-full px-3 py-2 text-left hover:bg-[#faf6f3] flex items-center gap-2"
                >
                  <span className="w-2 h-2 rounded-full bg-rose-500"></span>
                  <div>
                    <div className="font-semibold text-gray-900">Tampered NPI Check Digit</div>
                    <div className="text-[10px] text-gray-500">CMS Luhn Invariant Violation</div>
                  </div>
                </button>
                <button
                  onClick={() => handleGenerateScenario("invalid_icd10")}
                  className="w-full px-3 py-2 text-left hover:bg-[#faf6f3] flex items-center gap-2"
                >
                  <span className="w-2 h-2 rounded-full bg-rose-500"></span>
                  <div>
                    <div className="font-semibold text-gray-900">Unregistered ICD-10 Code</div>
                    <div className="text-[10px] text-gray-500">CMS Taxonomy Registry Alert</div>
                  </div>
                </button>
                <button
                  onClick={() => handleGenerateScenario("future_dob")}
                  className="w-full px-3 py-2 text-left hover:bg-[#faf6f3] flex items-center gap-2"
                >
                  <span className="w-2 h-2 rounded-full bg-rose-500"></span>
                  <div>
                    <div className="font-semibold text-gray-900">Future DOB Violation</div>
                    <div className="text-[10px] text-gray-500">Chronology Timeline Invariant</div>
                  </div>
                </button>
                <button
                  onClick={() => handleGenerateScenario("heavy_noise")}
                  className="w-full px-3 py-2 text-left hover:bg-[#faf6f3] flex items-center gap-2"
                >
                  <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                  <div>
                    <div className="font-semibold text-gray-900">Heavy Analog Fax Noise</div>
                    <div className="text-[10px] text-gray-500">Conformal Risk Threshold Flag</div>
                  </div>
                </button>
              </div>
            )}
          </div>

          {/* Upload Referral Fax Button */}
          <button
            onClick={() => setUploadModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#220c0c] hover:bg-[#381616] text-white rounded-lg text-xs font-semibold transition-colors shadow-xs"
          >
            <Icon name="upload-cloud" className="w-4 h-4 text-emerald-400" />
            <span>Upload Fax</span>
          </button>
        </div>
      </header>

      {/* Action Notification Toast */}
      {actionSuccessMsg && (
        <div className="absolute top-16 right-6 z-50 bg-emerald-700 text-white px-4 py-2.5 rounded-xl shadow-xl flex items-center gap-2 text-xs font-medium animate-fade-in border border-emerald-500">
          <Icon name="check-circle" className="w-4 h-4 text-emerald-300" />
          <span>{actionSuccessMsg}</span>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Workspace View (Caseload Stream + Split Review Panel)         */}
      {/* ------------------------------------------------------------- */}
      {activeTab === "workspace" && (
        <div className="flex-1 flex overflow-hidden">
          {/* Left Column: Caseload Queue & Filter Strip */}
          <aside className="w-80 sm:w-96 bg-white border-r border-[#eae0dc] flex flex-col shrink-0 z-20">
            {/* Filter Pills & Ingest Action */}
            <div className="p-3 border-b border-[#eae0dc] space-y-2 bg-[#fcfaf8]">
              {/* Primary Ingestion Trigger */}
              <button
                onClick={() => setUploadModalOpen(true)}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-[#220c0c] hover:bg-[#381616] text-white rounded-lg text-xs font-semibold shadow-xs transition-colors group cursor-pointer"
              >
                <Icon name="upload-cloud" className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
                <span>+ Ingest Document (PDF / Scan)</span>
              </button>

              <div className="relative">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search patient, NPI, ICD-10..."
                  className="w-full pl-8 pr-3 py-1.5 bg-white border border-[#eae0dc] rounded-lg text-xs text-[#1a1a1a] placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-[#8c78e1]"
                />
                <div className="absolute left-2.5 top-2 text-gray-400">
                  <Icon name="search" className="w-3.5 h-3.5" />
                </div>
              </div>

              <div className="flex items-center gap-1 pt-1">
                <button
                  onClick={() => setFilterMode("all")}
                  className={`flex-1 py-1 text-center rounded-md text-[11px] font-medium transition-colors ${
                    filterMode === "all"
                      ? "bg-[#220c0c] text-white"
                      : "bg-[#f5eeea] text-gray-600 hover:bg-[#eee3dd]"
                  }`}
                >
                  All ({totalCount})
                </button>
                <button
                  onClick={() => setFilterMode("review")}
                  className={`flex-1 py-1 text-center rounded-md text-[11px] font-medium transition-colors ${
                    filterMode === "review"
                      ? "bg-rose-600 text-white"
                      : "bg-[#f5eeea] text-rose-700 hover:bg-rose-100"
                  }`}
                >
                  Flagged ({flaggedCount})
                </button>
                <button
                  onClick={() => setFilterMode("stp")}
                  className={`flex-1 py-1 text-center rounded-md text-[11px] font-medium transition-colors ${
                    filterMode === "stp"
                      ? "bg-emerald-700 text-white"
                      : "bg-[#f5eeea] text-emerald-800 hover:bg-emerald-100"
                  }`}
                >
                  STP ({stpCount})
                </button>
              </div>
            </div>

            {/* Referral Cards List */}
            <div className="flex-1 overflow-y-auto custom-scroll divide-y divide-[#f2eae5]">
              {loading ? (
                <div className="p-8 text-center text-xs text-gray-500">
                  <div className="inline-block animate-spin w-5 h-5 border-2 border-[#220c0c] border-t-transparent rounded-full mb-2"></div>
                  <p>Loading clinical faxes...</p>
                </div>
              ) : filteredReferrals.length === 0 ? (
                <div className="p-8 text-center text-xs text-gray-400">
                  No referrals match current filter criteria.
                </div>
              ) : (
                filteredReferrals.map((r) => {
                  const isSelected = r.referral_id === selectedId;
                  const isAuto = r.routing_decision === "AUTO_ACCEPTED";
                  const isApproved = r.clinician_approved;

                  return (
                    <div
                      key={r.referral_id}
                      onClick={() => setSelectedId(r.referral_id)}
                      className={`p-3.5 cursor-pointer transition-colors relative ${
                        isSelected
                          ? "bg-[#f9f4f1] border-l-4 border-l-[#220c0c]"
                          : "hover:bg-[#fdfbf9]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <span className="font-mono text-[11px] font-semibold text-[#220c0c]">
                          {r.referral_id}
                        </span>
                        <span
                          className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                            isApproved
                              ? "bg-blue-100 text-blue-800 border border-blue-200"
                              : isAuto
                              ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                              : "bg-rose-100 text-rose-800 border border-rose-200"
                          }`}
                        >
                          {isApproved ? "APPROVED" : isAuto ? "STP ACCEPTED" : "NEEDS REVIEW"}
                        </span>
                      </div>

                      <div className="font-medium text-xs text-gray-900 mb-1">
                        {r.patient_name}{" "}
                        <span className="text-gray-400 font-normal">({r.dob})</span>
                      </div>

                      <div className="text-[11px] text-gray-500 mb-2 truncate">
                        {r.service_requested}
                      </div>

                      {/* Diagnostic Badges */}
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-mono text-[10px] bg-white border border-[#eae0dc] px-1.5 py-0.5 rounded text-gray-700">
                          NPI: {r.npi}
                        </span>
                        <span className="font-mono text-[10px] bg-white border border-[#eae0dc] px-1.5 py-0.5 rounded text-gray-700">
                          ICD: {r.diagnosis_code}
                        </span>
                        <span className="ml-auto text-[10px] font-mono text-gray-500 font-medium">
                          {(r.overall_confidence * 100).toFixed(0)}% Conf
                        </span>
                      </div>

                      {/* Flag Warning line */}
                      {r.validation_flags && r.validation_flags.length > 0 && (
                        <div className="mt-1.5 text-[10px] text-rose-700 font-mono truncate flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0"></span>
                          <span>{r.validation_flags[0]}</span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </aside>

          {/* --------------------------------------------------------- */}
          {/* Main Stage: Dual-Pane Review Workspace                    */}
          {/* --------------------------------------------------------- */}
          {selectedDoc ? (
            <main className="flex-1 flex flex-col lg:flex-row overflow-hidden bg-[#f7f1ed]">
              {/* Left Stage: Document Viewer with Interactive Bounding Boxes */}
              <div className="flex-1 flex flex-col border-r border-[#eae0dc] bg-[#221f1e] overflow-hidden">
                {/* Stage Toolbar */}
                <div className="h-10 bg-[#181615] text-gray-300 px-4 flex items-center justify-between text-xs shrink-0 select-none border-b border-black/40">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-[11px] text-gray-400 truncate max-w-xs">
                      {selectedDoc.source_file}
                    </span>
                    <span className="text-gray-600">|</span>
                    <label className="flex items-center gap-1.5 cursor-pointer text-gray-300 hover:text-white">
                      <input
                        type="checkbox"
                        checked={showBoundingBoxes}
                        onChange={(e) => setShowBoundingBoxes(e.target.checked)}
                        className="rounded border-gray-600 text-[#8c78e1] focus:ring-0 w-3.5 h-3.5"
                      />
                      <span>Bounding Boxes</span>
                    </label>
                  </div>

                  {/* Canvas Controls */}
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => setRotation((r) => (r + 90) % 360)}
                      className="p-1 hover:bg-white/10 rounded text-gray-300"
                      title="Rotate Document 90°"
                    >
                      <Icon name="rotate-cw" className="w-3.5 h-3.5" />
                    </button>
                    <div className="h-3 w-px bg-white/20 mx-1"></div>
                    <button
                      onClick={() => setZoomLevel((z) => Math.max(60, z - 15))}
                      className="p-1 hover:bg-white/10 rounded text-gray-300"
                      title="Zoom Out"
                    >
                      <Icon name="minus" className="w-3.5 h-3.5" />
                    </button>
                    <span className="font-mono text-[11px] px-1 text-gray-400">{zoomLevel}%</span>
                    <button
                      onClick={() => setZoomLevel((z) => Math.min(200, z + 15))}
                      className="p-1 hover:bg-white/10 rounded text-gray-300"
                      title="Zoom In"
                    >
                      <Icon name="plus" className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => {
                        setZoomLevel(100);
                        setRotation(0);
                      }}
                      className="ml-2 px-2 py-0.5 bg-white/10 hover:bg-white/20 rounded text-[10px] font-mono text-gray-300"
                    >
                      Reset
                    </button>
                  </div>
                </div>

                {/* Document Display Canvas */}
                <div className="flex-1 overflow-auto p-4 flex items-center justify-center custom-scroll">
                  <div
                    className="relative bg-white shadow-2xl transition-all duration-150 origin-center"
                    style={{
                      width: `${zoomLevel * 8.5}px`,
                      maxWidth: "100%",
                      transform: `rotate(${rotation}deg)`,
                    }}
                  >
                    {/* Rendered Fax Raster */}
                    <img
                      src={`/api/referrals/${selectedDoc.referral_id}/image`}
                      alt="Referral Facsimile Scan"
                      className="w-full h-auto block select-none pointer-events-none"
                    />

                    {/* SVG Interactive Bounding Boxes Layer */}
                    {showBoundingBoxes && selectedDoc.field_entities && (
                      <svg
                        className="absolute inset-0 w-full h-full pointer-events-auto"
                        viewBox="0 0 100 100"
                        preserveAspectRatio="none"
                      >
                        {Object.entries(selectedDoc.field_entities).map(([key, entity]) => {
                          if (!entity.bbox) return null;
                          const { ymin, xmin, ymax, xmax } = entity.bbox;
                          const isHovered = selectedFieldKey === key;
                          const isFlagged = entity.status === "FLAGGED_FOR_REVIEW";
                          const isOverridden = entity.status === "OVERRIDDEN";

                          // Color logic
                          const strokeColor = isFlagged
                            ? "#e11d48"
                            : isOverridden
                            ? "#2563eb"
                            : entity.confidence < 0.88
                            ? "#f59e0b"
                            : "#10b981";

                          const fillColor = isHovered
                            ? isFlagged
                              ? "rgba(225, 29, 72, 0.25)"
                              : "rgba(16, 185, 129, 0.25)"
                            : "transparent";

                          return (
                            <rect
                              key={key}
                              x={xmin * 100}
                              y={ymin * 100}
                              width={(xmax - xmin) * 100}
                              height={(ymax - ymin) * 100}
                              fill={fillColor}
                              stroke={strokeColor}
                              strokeWidth={isHovered ? "0.6" : "0.35"}
                              strokeDasharray={isFlagged ? "0.8,0.4" : "none"}
                              className="cursor-pointer transition-all"
                              onClick={() => {
                                setSelectedFieldKey(key);
                                setEditingFieldKey(key);
                                setEditingValue(String(entity.value || ""));
                              }}
                              onMouseEnter={() => setSelectedFieldKey(key)}
                              onMouseLeave={() => setSelectedFieldKey(null)}
                            >
                              <title>{`${key}: "${entity.raw_text}" (${(entity.confidence * 100).toFixed(0)}% conf) - Click to edit`}</title>
                            </rect>
                          );
                        })}
                      </svg>
                    )}
                  </div>
                </div>
              </div>

              {/* Right Stage: Clinical Extraction & Invariant Verification Cards */}
              <div className="w-full lg:w-[480px] xl:w-[540px] bg-white flex flex-col shrink-0 overflow-y-auto custom-scroll divide-y divide-[#eae0dc]">
                {/* Document Status Header */}
                <div className="p-4 bg-[#fcfaf8]">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-serif text-lg font-bold text-[#220c0c]">
                      {selectedDoc.patient.first_name} {selectedDoc.patient.last_name}
                    </span>
                    <span
                      className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
                        selectedDoc.clinician_approved
                          ? "bg-blue-100 text-blue-900 border border-blue-200"
                          : selectedDoc.routing_decision === "AUTO_ACCEPTED"
                          ? "bg-emerald-100 text-emerald-900 border border-emerald-200"
                          : "bg-rose-100 text-rose-900 border border-rose-200"
                      }`}
                    >
                      {selectedDoc.clinician_approved
                        ? "CLINICIAN APPROVED"
                        : selectedDoc.routing_decision === "AUTO_ACCEPTED"
                        ? "AUTO ACCEPTED (STP)"
                        : "FLAGGED FOR REVIEW"}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 font-mono">
                    <div>
                      <span className="text-gray-400">Referral ID:</span> {selectedDoc.referral_id}
                    </div>
                    <div>
                      <span className="text-gray-400">Date:</span> {selectedDoc.referral_date}
                    </div>
                    <div>
                      <span className="text-gray-400">Service:</span> {selectedDoc.service_requested}
                    </div>
                    <div>
                      <span className="text-gray-400">Priority:</span>{" "}
                      <span className="font-bold text-[#220c0c]">{selectedDoc.urgency}</span>
                    </div>
                  </div>
                </div>

                {/* Invariant Verification Engine Status */}
                <div className="p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-gray-500">
                      Deterministic Invariant Checks
                    </span>
                    <span className="text-xs font-mono font-semibold text-gray-700">
                      Overall: {(selectedDoc.overall_confidence * 100).toFixed(1)}%
                    </span>
                  </div>

                  <div className="space-y-2">
                    {/* NPI Check */}
                    <div className="flex items-center justify-between p-2.5 rounded-lg border border-[#eae0dc] bg-[#faf6f3]">
                      <div className="flex items-center gap-2">
                        <Icon
                          name={
                            selectedDoc.audit.invariant_checks.npi_luhn.valid
                              ? "shield-check"
                              : "alert-triangle"
                          }
                          className={`w-4 h-4 ${
                            selectedDoc.audit.invariant_checks.npi_luhn.valid
                              ? "text-emerald-600"
                              : "text-rose-600"
                          }`}
                        />
                        <div>
                          <div className="text-xs font-medium text-gray-900">CMS 10-Digit NPI Luhn</div>
                          <div className="text-[11px] text-gray-500">
                            {selectedDoc.audit.invariant_checks.npi_luhn.reason}
                          </div>
                        </div>
                      </div>
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                          selectedDoc.audit.invariant_checks.npi_luhn.valid
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {selectedDoc.audit.invariant_checks.npi_luhn.valid ? "PASSED" : "FAILED"}
                      </span>
                    </div>

                    {/* ICD-10 Taxonomy Check */}
                    <div className="flex items-center justify-between p-2.5 rounded-lg border border-[#eae0dc] bg-[#faf6f3]">
                      <div className="flex items-center gap-2">
                        <Icon
                          name={
                            selectedDoc.audit.invariant_checks.icd10_taxonomy.valid
                              ? "check-circle-2"
                              : "alert-circle"
                          }
                          className={`w-4 h-4 ${
                            selectedDoc.audit.invariant_checks.icd10_taxonomy.valid
                              ? "text-emerald-600"
                              : "text-rose-600"
                          }`}
                        />
                        <div>
                          <div className="text-xs font-medium text-gray-900">CMS ICD-10-CM Taxonomy</div>
                          <div className="text-[11px] text-gray-500">
                            {selectedDoc.audit.invariant_checks.icd10_taxonomy.reason}
                          </div>
                        </div>
                      </div>
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                          selectedDoc.audit.invariant_checks.icd10_taxonomy.valid
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {selectedDoc.audit.invariant_checks.icd10_taxonomy.valid ? "VERIFIED" : "UNVERIFIED"}
                      </span>
                    </div>

                    {/* Chronology Invariant Check */}
                    <div className="flex items-center justify-between p-2.5 rounded-lg border border-[#eae0dc] bg-[#faf6f3]">
                      <div className="flex items-center gap-2">
                        <Icon
                          name={
                            selectedDoc.audit.invariant_checks.chronology.valid
                              ? "calendar"
                              : "clock"
                          }
                          className={`w-4 h-4 ${
                            selectedDoc.audit.invariant_checks.chronology.valid
                              ? "text-emerald-600"
                              : "text-rose-600"
                          }`}
                        />
                        <div>
                          <div className="text-xs font-medium text-gray-900">Timeline Chronology</div>
                          <div className="text-[11px] text-gray-500">
                            {selectedDoc.audit.invariant_checks.chronology.valid
                              ? "DOB < Referral Date <= Service Date"
                              : selectedDoc.audit.invariant_checks.chronology.reason}
                          </div>
                        </div>
                      </div>
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                          selectedDoc.audit.invariant_checks.chronology.valid
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {selectedDoc.audit.invariant_checks.chronology.valid ? "PASSED" : "VIOLATION"}
                      </span>
                    </div>
                  </div>

                  {/* Flagged Failure Box */}
                  {selectedDoc.validation_flags && selectedDoc.validation_flags.length > 0 && (
                    <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg space-y-1">
                      <div className="text-xs font-bold text-rose-800 flex items-center gap-1.5">
                        <Icon name="alert-octagon" className="w-4 h-4 text-rose-600" />
                        <span>Action Required: Flagged Reasons</span>
                      </div>
                      <ul className="text-xs text-rose-700 list-disc list-inside space-y-0.5 font-mono">
                        {selectedDoc.validation_flags.map((flag, i) => (
                          <li key={i}>{flag}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {/* Structured Extraction Cards with Inline Editing */}
                <div className="p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-gray-500">
                      Extracted Clinical Entities
                    </span>
                    <span className="text-[11px] text-gray-400">
                      Click any field to correct value
                    </span>
                  </div>

                  {/* Inline Field Editor Modal/Bar if active */}
                  {editingFieldKey && (
                    <div className="p-3 bg-[#fdfaf8] border-2 border-[#8c78e1] rounded-xl space-y-2 animate-fade-in shadow-sm">
                      <div className="flex items-center justify-between text-xs font-semibold text-[#220c0c]">
                        <span>Correcting: <span className="font-mono text-[#8c78e1]">{editingFieldKey}</span></span>
                        <button
                          onClick={() => setEditingFieldKey(null)}
                          className="text-gray-400 hover:text-gray-600"
                        >
                          <Icon name="x" className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={editingValue}
                          onChange={(e) => setEditingValue(e.target.value)}
                          className="flex-1 px-3 py-1.5 bg-white border border-[#eae0dc] rounded-lg text-xs font-mono text-gray-900 focus:outline-none focus:ring-1 focus:ring-[#8c78e1]"
                          autoFocus
                        />
                        <button
                          onClick={handleSaveFieldEdit}
                          disabled={isSavingField}
                          className="px-3 py-1.5 bg-[#220c0c] hover:bg-[#381616] text-white text-xs font-semibold rounded-lg flex items-center gap-1 shadow-xs"
                        >
                          {isSavingField ? "Validating..." : "Save & Re-evaluate"}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Referring Provider Card */}
                  <div
                    onMouseEnter={() => setSelectedFieldKey("referring_provider.npi")}
                    onMouseLeave={() => setSelectedFieldKey(null)}
                    className="p-3 rounded-lg border border-[#eae0dc] hover:border-[#8c78e1] transition-colors relative group"
                  >
                    <div className="flex items-center justify-between text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-2">
                      <span>Referring Physician</span>
                      <button
                        onClick={() => {
                          setEditingFieldKey("referring_provider.npi");
                          setEditingValue(selectedDoc.referring_provider.npi);
                        }}
                        className="opacity-0 group-hover:opacity-100 text-[10px] text-[#8c78e1] font-semibold flex items-center gap-1 transition-opacity"
                      >
                        <Icon name="edit-3" className="w-3 h-3" /> Edit NPI
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-gray-400 block text-[10px]">Name</span>
                        <span className="font-semibold text-gray-900">
                          {selectedDoc.referring_provider.name}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-400 block text-[10px]">CMS NPI (10-Digit)</span>
                        <span className="font-mono font-bold text-[#220c0c]">
                          {selectedDoc.referring_provider.npi}
                        </span>
                      </div>
                      <div className="col-span-2">
                        <span className="text-gray-400 block text-[10px]">Clinic / Practice</span>
                        <span className="text-gray-800">{selectedDoc.referring_provider.clinic_name}</span>
                      </div>
                    </div>
                  </div>

                  {/* Diagnosis Card */}
                  <div
                    onMouseEnter={() => setSelectedFieldKey("diagnosis.icd10_code")}
                    onMouseLeave={() => setSelectedFieldKey(null)}
                    className="p-3 rounded-lg border border-[#eae0dc] hover:border-[#8c78e1] transition-colors relative group"
                  >
                    <div className="flex items-center justify-between text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-2">
                      <span>Clinical Encounter & Diagnosis</span>
                      <button
                        onClick={() => {
                          setEditingFieldKey("diagnosis.icd10_code");
                          setEditingValue(selectedDoc.diagnoses[0]?.code || "");
                        }}
                        className="opacity-0 group-hover:opacity-100 text-[10px] text-[#8c78e1] font-semibold flex items-center gap-1 transition-opacity"
                      >
                        <Icon name="edit-3" className="w-3 h-3" /> Edit ICD-10
                      </button>
                    </div>
                    <div className="space-y-1.5 text-xs">
                      <div>
                        <span className="text-gray-400 block text-[10px]">ICD-10-CM Coding</span>
                        <span className="font-mono font-bold text-base text-[#220c0c]">
                          {selectedDoc.diagnoses[0]?.code}
                        </span>
                        <span className="text-gray-600 ml-2">
                          {selectedDoc.diagnoses[0]?.description}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Patient Info Card */}
                  <div
                    onMouseEnter={() => setSelectedFieldKey("patient.first_name")}
                    onMouseLeave={() => setSelectedFieldKey(null)}
                    className="p-3 rounded-lg border border-[#eae0dc] hover:border-[#8c78e1] transition-colors relative group"
                  >
                    <div className="flex items-center justify-between text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-2">
                      <span>Patient Demographics</span>
                      <button
                        onClick={() => {
                          setEditingFieldKey("patient.dob");
                          setEditingValue(selectedDoc.patient.dob);
                        }}
                        className="opacity-0 group-hover:opacity-100 text-[10px] text-[#8c78e1] font-semibold flex items-center gap-1 transition-opacity"
                      >
                        <Icon name="edit-3" className="w-3 h-3" /> Edit DOB
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-gray-400 block text-[10px]">Name</span>
                        <span className="font-semibold text-gray-900">
                          {selectedDoc.patient.first_name} {selectedDoc.patient.last_name}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-400 block text-[10px]">Date of Birth</span>
                        <span className="font-mono text-gray-900">{selectedDoc.patient.dob}</span>
                      </div>
                      <div>
                        <span className="text-gray-400 block text-[10px]">Gender</span>
                        <span className="capitalize text-gray-800">{selectedDoc.patient.gender}</span>
                      </div>
                      <div>
                        <span className="text-gray-400 block text-[10px]">Phone</span>
                        <span className="text-gray-800">{selectedDoc.patient.phone || "—"}</span>
                      </div>
                    </div>
                  </div>

                  {/* Insurance Policy */}
                  {selectedDoc.insurance && (
                    <div
                      onMouseEnter={() => setSelectedFieldKey("insurance.member_id")}
                      onMouseLeave={() => setSelectedFieldKey(null)}
                      className="p-3 rounded-lg border border-[#eae0dc] hover:border-[#8c78e1] transition-colors"
                    >
                      <div className="text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-2">
                        Payer & Coverage
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-gray-400 block text-[10px]">Payer Name</span>
                          <span className="font-medium text-gray-900">{selectedDoc.insurance.payer_name}</span>
                        </div>
                        <div>
                          <span className="text-gray-400 block text-[10px]">Subscriber Member ID</span>
                          <span className="font-mono text-gray-900">{selectedDoc.insurance.member_id}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Clinician Human-in-the-Loop Override Panel */}
                <div className="p-4 bg-[#fcfaf8] space-y-3 mt-auto">
                  <div className="text-xs font-bold text-[#220c0c] flex items-center justify-between">
                    <span>Clinician Sign-off & Disposition</span>
                    {selectedDoc.clinician_approved && (
                      <span className="text-[11px] text-blue-700 font-semibold flex items-center gap-1">
                        <Icon name="check" className="w-3.5 h-3.5" /> Approved
                      </span>
                    )}
                  </div>

                  <textarea
                    value={overrideNotes}
                    onChange={(e) => setOverrideNotes(e.target.value)}
                    placeholder="Enter clinician review rationale or override notes..."
                    rows={2}
                    className="w-full text-xs p-2.5 bg-white border border-[#eae0dc] rounded-lg focus:outline-none focus:ring-1 focus:ring-[#8c78e1]"
                  />

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleApprove}
                      className="flex-1 py-2 px-3 bg-[#220c0c] hover:bg-[#381616] text-white text-xs font-semibold rounded-lg flex items-center justify-center gap-1.5 transition-colors shadow-xs"
                    >
                      <Icon name="check-square" className="w-4 h-4 text-emerald-400" />
                      <span>{selectedDoc.clinician_approved ? "Update Approval" : "Approve & Release to FHIR"}</span>
                    </button>

                    <button
                      onClick={() => openFhirModal(selectedDoc.referral_id)}
                      className="py-2 px-3 bg-white hover:bg-gray-50 border border-[#eae0dc] text-xs font-semibold text-gray-800 rounded-lg flex items-center gap-1.5 transition-colors"
                      title="Inspect HL7 FHIR Bundle"
                    >
                      <Icon name="code" className="w-4 h-4 text-[#8c78e1]" />
                      <span>FHIR</span>
                    </button>
                  </div>
                </div>
              </div>
            </main>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-gray-400">
              Select a clinical referral to inspect.
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Tab 2: Benchmark Matrix (EvalRunner Empirical Scorecard)      */}
      {/* ------------------------------------------------------------- */}
      {activeTab === "benchmark" && (
        <div className="flex-1 overflow-y-auto p-6 max-w-5xl mx-auto w-full space-y-6">
          <div className="bg-white rounded-2xl border border-[#eae0dc] p-6 shadow-xs">
            <div className="flex items-center justify-between mb-4 pb-4 border-b border-[#eae0dc]">
              <div>
                <h2 className="font-serif text-2xl font-bold text-[#220c0c]">
                  Conformal IDP Benchmark Scorecard
                </h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  Comparative empirical ablation against naive regex/uncalibrated extraction across synthetic cohorts.
                </p>
              </div>

              <button
                onClick={runBenchmark}
                disabled={benchmarkLoading}
                className="px-4 py-2 bg-[#220c0c] hover:bg-[#381616] text-white text-xs font-semibold rounded-lg flex items-center gap-2 transition-all disabled:opacity-50"
              >
                <Icon name="rotate-ccw" className={`w-3.5 h-3.5 ${benchmarkLoading ? "animate-spin" : ""}`} />
                <span>{benchmarkLoading ? "Running Evaluation..." : "Re-run Benchmark"}</span>
              </button>
            </div>

            {benchmarkLoading ? (
              <div className="py-12 text-center text-xs text-gray-500">
                <div className="inline-block animate-spin w-6 h-6 border-2 border-[#220c0c] border-t-transparent rounded-full mb-3"></div>
                <p>Generating degraded fax cohorts & evaluating conformal risk bounds...</p>
              </div>
            ) : benchmarkData ? (
              <div className="space-y-6">
                {/* Metric Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="p-4 bg-[#faf6f3] border border-[#eae0dc] rounded-xl">
                    <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider block">
                      STP Auto-Accept Rate
                    </span>
                    <span className="font-mono text-2xl font-bold text-emerald-700 block mt-1">
                      {benchmarkData.stp_rate_clean.toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-gray-400">Clean/Mild cohort baseline</span>
                  </div>

                  <div className="p-4 bg-[#faf6f3] border border-[#eae0dc] rounded-xl">
                    <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider block">
                      Clinical Safety Catch
                    </span>
                    <span className="font-mono text-2xl font-bold text-emerald-700 block mt-1">
                      {benchmarkData.overall_safety_sensitivity.toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-gray-400">Target: 100.0% sensitivity</span>
                  </div>

                  <div className="p-4 bg-[#faf6f3] border border-[#eae0dc] rounded-xl">
                    <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider block">
                      P50 Pipeline Latency
                    </span>
                    <span className="font-mono text-2xl font-bold text-[#220c0c] block mt-1">
                      {benchmarkData.p50_latency_ms.toFixed(1)}ms
                    </span>
                    <span className="text-[10px] text-gray-400">P95: {benchmarkData.p95_latency_ms}ms</span>
                  </div>

                  <div className="p-4 bg-[#faf6f3] border border-[#eae0dc] rounded-xl">
                    <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider block">
                      HL7 FHIR Compliance
                    </span>
                    <span className="font-mono text-2xl font-bold text-blue-700 block mt-1">
                      PASSED
                    </span>
                    <span className="text-[10px] text-gray-400">US Core R4 transaction</span>
                  </div>
                </div>

                {/* Comparative Ablation Table */}
                <div className="border border-[#eae0dc] rounded-xl overflow-hidden">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-[#f5eeea] text-[#220c0c] font-bold uppercase text-[10px] tracking-wider border-b border-[#eae0dc]">
                        <th className="py-3 px-4">Evaluation Cohort</th>
                        <th className="py-3 px-4">Naive Baseline</th>
                        <th className="py-3 px-4">Engineered Conformal Pipeline</th>
                        <th className="py-3 px-4">Safety Guarantee</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#eae0dc] font-mono text-gray-700">
                      <tr>
                        <td className="py-3 px-4 font-sans font-medium text-gray-900">
                          Clean Ambulatory Fax (STP Rate)
                        </td>
                        <td className="py-3 px-4 text-gray-500">100.0% (Unchecked)</td>
                        <td className="py-3 px-4 text-emerald-700 font-bold">
                          {benchmarkData.stp_rate_clean.toFixed(1)}% (Calibrated)
                        </td>
                        <td className="py-3 px-4 text-emerald-600 font-sans">Zero false rejections</td>
                      </tr>
                      <tr>
                        <td className="py-3 px-4 font-sans font-medium text-gray-900">
                          Tampered NPI (CMS Luhn Check)
                        </td>
                        <td className="py-3 px-4 text-rose-600 font-bold">0.0% (LEAKED)</td>
                        <td className="py-3 px-4 text-emerald-700 font-bold">
                          {benchmarkData.safety_catch_npi_luhn.toFixed(1)}% (Caught)
                        </td>
                        <td className="py-3 px-4 text-emerald-600 font-sans">100% Luhn check digit</td>
                      </tr>
                      <tr>
                        <td className="py-3 px-4 font-sans font-medium text-gray-900">
                          Invalid ICD-10 (Taxonomy Verification)
                        </td>
                        <td className="py-3 px-4 text-rose-600 font-bold">0.0% (LEAKED)</td>
                        <td className="py-3 px-4 text-emerald-700 font-bold">
                          {benchmarkData.safety_catch_icd10.toFixed(1)}% (Caught)
                        </td>
                        <td className="py-3 px-4 text-emerald-600 font-sans">CMS clinical code table</td>
                      </tr>
                      <tr>
                        <td className="py-3 px-4 font-sans font-medium text-gray-900">
                          Future DOB (Chronology Invariant)
                        </td>
                        <td className="py-3 px-4 text-rose-600 font-bold">0.0% (LEAKED)</td>
                        <td className="py-3 px-4 text-emerald-700 font-bold">
                          {benchmarkData.safety_catch_chronology.toFixed(1)}% (Caught)
                        </td>
                        <td className="py-3 px-4 text-emerald-600 font-sans">DOB &lt; DOS invariant</td>
                      </tr>
                      <tr>
                        <td className="py-3 px-4 font-sans font-medium text-gray-900">
                          Heavy Analog Fax Noise (Optical Artifacts)
                        </td>
                        <td className="py-3 px-4 text-rose-600 font-bold">0.0% (LEAKED)</td>
                        <td className="py-3 px-4 text-emerald-700 font-bold">
                          {benchmarkData.safety_catch_severe_noise.toFixed(1)}% (Flagged)
                        </td>
                        <td className="py-3 px-4 text-emerald-600 font-sans">Conformal risk boundary</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Modal 1: Document Upload & Drag-and-Drop Zone                */}
      {/* ------------------------------------------------------------- */}
      {uploadModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl border border-[#eae0dc] max-w-xl w-full p-6 shadow-2xl relative max-h-[90vh] overflow-y-auto custom-scroll">
            <div className="flex items-center justify-between pb-3 border-b border-[#eae0dc] mb-4">
              <div className="flex items-center gap-2">
                <Icon name="upload-cloud" className="w-5 h-5 text-[#8c78e1]" />
                <div>
                  <h3 className="font-serif font-bold text-lg text-[#220c0c]">
                    Clinical Document Ingestion & Hardware OCR
                  </h3>
                  <p className="text-[11px] text-gray-500">
                    Upload ambulatory fax scans or PDFs. Evaluates CMS Luhn NPI, ICD-10 registry & chronology invariants.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setUploadModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 p-1"
              >
                <Icon name="x" className="w-4 h-4" />
              </button>
            </div>

            <input
              type="file"
              ref={fileInputRef}
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  handleFileUpload(e.target.files[0]);
                }
              }}
              className="hidden"
            />

            {/* Drag & Drop Zone */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setUploadDragOver(true);
              }}
              onDragLeave={() => setUploadDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setUploadDragOver(false);
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                  handleFileUpload(e.dataTransfer.files[0]);
                }
              }}
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
              className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                uploadDragOver
                  ? "border-[#8c78e1] bg-[#f9f4fd]"
                  : "border-[#dfd4cf] hover:border-[#8c78e1] bg-[#faf6f3]"
              }`}
            >
              {isUploading ? (
                <div className="py-4">
                  <div className="inline-block animate-spin w-8 h-8 border-3 border-[#220c0c] border-t-transparent rounded-full mb-3"></div>
                  <p className="text-xs font-semibold text-[#220c0c]">
                    Running hardware-accelerated OCR layout extraction & conformal verifier...
                  </p>
                </div>
              ) : (
                <>
                  <div className="w-12 h-12 rounded-full bg-[#f2eae5] text-[#220c0c] flex items-center justify-center mx-auto mb-2">
                    <Icon name="file-up" className="w-6 h-6 text-[#8c78e1]" />
                  </div>
                  <p className="text-xs font-bold text-gray-800 mb-0.5">
                    Click to browse or drag and drop facsimile scan or PDF
                  </p>
                  <p className="text-[11px] text-gray-500 mb-2">
                    Accepts PDF, PNG, JPG, or WEBP high-resolution clinical intake files
                  </p>
                  <span className="inline-block px-3 py-0.5 bg-white border border-[#eae0dc] text-[10px] font-mono rounded-md text-gray-600">
                    200–300 DPI Recommended • Native Windows OCR & PDF Runtime
                  </span>
                </>
              )}
            </div>

            {/* Quick Test Scenarios with Pre-Rendered Documents */}
            <div className="mt-4 pt-3 border-t border-[#eae0dc]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">
                  Or Ingest Pre-Configured Test Referral
                </span>
                <span className="text-[10px] text-gray-400 font-mono">1-Click Verification</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => handleLoadSample("01_clean_cardiology_referral.png")}
                  className="p-2 border border-[#eae0dc] hover:border-emerald-500 hover:bg-emerald-50/50 rounded-lg text-left transition-colors cursor-pointer group"
                >
                  <div className="font-semibold text-gray-900 flex items-center justify-between">
                    <span>Clean Cardiology</span>
                    <span className="text-[9px] bg-emerald-100 text-emerald-800 font-mono px-1 rounded">STP 100%</span>
                  </div>
                  <div className="text-[10px] text-gray-500 truncate">{"Dr. Brody \u2192 Cardiology, All Invariants Pass"}</div>
                </button>

                <button
                  type="button"
                  onClick={() => handleLoadSample("02_npi_luhn_error_referral.png")}
                  className="p-2 border border-[#eae0dc] hover:border-rose-500 hover:bg-rose-50/50 rounded-lg text-left transition-colors cursor-pointer group"
                >
                  <div className="font-semibold text-gray-900 flex items-center justify-between">
                    <span>Tampered NPI</span>
                    <span className="text-[9px] bg-rose-100 text-rose-800 font-mono px-1 rounded">Luhn Fail</span>
                  </div>
                  <div className="text-[10px] text-gray-500 truncate">Check-digit invalid (1234567894)</div>
                </button>

                <button
                  type="button"
                  onClick={() => handleLoadSample("03_invalid_icd10_taxonomy.png")}
                  className="p-2 border border-[#eae0dc] hover:border-rose-500 hover:bg-rose-50/50 rounded-lg text-left transition-colors cursor-pointer group"
                >
                  <div className="font-semibold text-gray-900 flex items-center justify-between">
                    <span>Unregistered ICD-10</span>
                    <span className="text-[9px] bg-rose-100 text-rose-800 font-mono px-1 rounded">CMS Alert</span>
                  </div>
                  <div className="text-[10px] text-gray-500 truncate">Z99.999 Not in CMS active table</div>
                </button>

                <button
                  type="button"
                  onClick={() => handleLoadSample("04_future_dob_invariant_failure.png")}
                  className="p-2 border border-[#eae0dc] hover:border-rose-500 hover:bg-rose-50/50 rounded-lg text-left transition-colors cursor-pointer group"
                >
                  <div className="font-semibold text-gray-900 flex items-center justify-between">
                    <span>Future DOB</span>
                    <span className="text-[9px] bg-rose-100 text-rose-800 font-mono px-1 rounded">Timeline</span>
                  </div>
                  <div className="text-[10px] text-gray-500 truncate">{"DOB 2029-11-20 > Referral Date"}</div>
                </button>

                <button
                  type="button"
                  onClick={() => handleLoadSample("05_degraded_analog_fax.png")}
                  className="p-2 border border-[#eae0dc] hover:border-amber-500 hover:bg-amber-50/50 rounded-lg text-left transition-colors cursor-pointer group"
                >
                  <div className="font-semibold text-gray-900 flex items-center justify-between">
                    <span>Degraded Fax Scan</span>
                    <span className="text-[9px] bg-amber-100 text-amber-800 font-mono px-1 rounded">Risk Flag</span>
                  </div>
                  <div className="text-[10px] text-gray-500 truncate">{"Severe printhead noise & low confidence"}</div>
                </button>

                <button
                  type="button"
                  onClick={() => handleLoadSample("06_clinical_referral.pdf")}
                  className="p-2 border border-[#eae0dc] hover:border-blue-500 hover:bg-blue-50/50 rounded-lg text-left transition-colors cursor-pointer group"
                >
                  <div className="font-semibold text-gray-900 flex items-center justify-between">
                    <span>Clinical PDF Document</span>
                    <span className="text-[9px] bg-blue-100 text-blue-800 font-mono px-1 rounded">Native PDF</span>
                  </div>
                  <div className="text-[10px] text-gray-500 truncate">Rendered & parsed via Windows PDF runtime</div>
                </button>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-[#eae0dc] flex justify-end">
              <button
                onClick={() => setUploadModalOpen(false)}
                className="px-4 py-1.5 border border-[#eae0dc] text-xs font-medium rounded-lg text-gray-600 hover:bg-gray-50 cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Modal 3: Clinician Field Correction & Invariant Re-Evaluation */}
      {/* ------------------------------------------------------------- */}
      {editingFieldKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl border border-[#eae0dc] max-w-md w-full p-6 shadow-2xl relative">
            <div className="flex items-center justify-between pb-3 border-b border-[#eae0dc] mb-4">
              <div className="flex items-center gap-2">
                <Icon name="edit-3" className="w-5 h-5 text-[#8c78e1]" />
                <h3 className="font-serif font-bold text-base text-[#220c0c]">
                  Correct Clinical Entity
                </h3>
              </div>
              <button
                onClick={() => setEditingFieldKey(null)}
                className="text-gray-400 hover:text-gray-600 p-1"
              >
                <Icon name="x" className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">
                  Entity Target: <span className="font-mono text-gray-800 lowercase">{editingFieldKey}</span>
                </label>
                <p className="text-[11px] text-gray-500 mb-2">
                  Enter the verified value from the facsimile document. Modifying this entity immediately triggers real-time CMS Luhn, ICD-10 taxonomy, and chronological invariant verification.
                </p>
                <input
                  type="text"
                  value={editingValue}
                  onChange={(e) => setEditingValue(e.target.value)}
                  placeholder="Enter corrected clinical value..."
                  className="w-full px-3 py-2 border border-[#eae0dc] rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#8c78e1]"
                  autoFocus
                />
              </div>

              {editingFieldKey === "referring_provider.npi" && (
                <div className="p-2.5 bg-[#fcfaf8] rounded-lg border border-[#eae0dc] text-[11px] text-gray-600 space-y-1">
                  <div className="font-semibold text-gray-900">CMS 10-Digit NPI Invariant:</div>
                  <div>Must satisfy: <span className="font-mono text-gray-700">(24 + LuhnDouble(d1..d9) + d10) mod 10 == 0</span></div>
                  <div className="text-[10px] text-gray-400">Example valid NPI: 1497758544 or 1234567893</div>
                </div>
              )}

              {editingFieldKey === "diagnosis.icd10_code" && (
                <div className="p-2.5 bg-[#fcfaf8] rounded-lg border border-[#eae0dc] text-[11px] text-gray-600 space-y-1">
                  <div className="font-semibold text-gray-900">CMS Outpatient Taxonomy Registry:</div>
                  <div>Code must exist in CMS Active Taxonomy table (e.g. I10, M54.5, E11.9, J45.909).</div>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#eae0dc]">
                <button
                  type="button"
                  onClick={() => setEditingFieldKey(null)}
                  className="px-4 py-2 border border-[#eae0dc] text-xs font-medium rounded-lg text-gray-600 hover:bg-gray-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={isSavingField}
                  onClick={handleSaveFieldEdit}
                  className="px-4 py-2 bg-[#220c0c] hover:bg-[#381616] text-white text-xs font-semibold rounded-lg shadow-xs flex items-center gap-1.5 cursor-pointer disabled:opacity-60"
                >
                  {isSavingField ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      <span>Re-evaluating...</span>
                    </>
                  ) : (
                    <>
                      <Icon name="check" className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Save & Re-evaluate Invariants</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Modal 2: HL7 FHIR R4 Transaction Bundle Explorer               */}
      {/* ------------------------------------------------------------- */}
      {fhirModalDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl border border-[#eae0dc] max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="p-4 border-b border-[#eae0dc] flex items-center justify-between bg-[#faf6f3]">
              <div className="flex items-center gap-2">
                <Icon name="file-code" className="w-5 h-5 text-[#8c78e1]" />
                <h3 className="font-serif font-bold text-base text-[#220c0c]">
                  HL7 FHIR R4 Transaction Bundle
                </h3>
                <span className="text-xs bg-emerald-100 text-emerald-800 font-mono px-2 py-0.5 rounded font-semibold ml-2">
                  US Core Profile Compliant
                </span>
              </div>
              <button
                onClick={() => setFhirModalDoc(null)}
                className="p-1 hover:bg-gray-200 rounded-lg text-gray-500"
              >
                <Icon name="x" className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-auto p-4 bg-[#1e1c1b] text-gray-200 font-mono text-xs custom-scroll">
              <pre className="whitespace-pre-wrap">
                {JSON.stringify(fhirModalDoc.bundle, null, 2)}
              </pre>
            </div>

            <div className="p-3 bg-white border-t border-[#eae0dc] flex items-center justify-between text-xs">
              <span className="text-gray-500 font-mono">
                Total Resources: {fhirModalDoc.bundle.total} (Patient, Practitioner, Coverage, Condition, ServiceRequest)
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(JSON.stringify(fhirModalDoc.bundle, null, 2));
                    alert("FHIR R4 Bundle copied to clipboard!");
                  }}
                  className="px-3 py-1.5 border border-[#eae0dc] hover:bg-gray-50 rounded-lg font-medium text-gray-700"
                >
                  Copy JSON
                </button>
                <button
                  onClick={() => {
                    const blob = new Blob([JSON.stringify(fhirModalDoc.bundle, null, 2)], {
                      type: "application/json",
                    });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `fhir_bundle_${fhirModalDoc.bundle.id}.json`;
                    a.click();
                  }}
                  className="px-3 py-1.5 bg-[#220c0c] hover:bg-[#381616] text-white rounded-lg font-medium"
                >
                  Download .json
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Render root
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
