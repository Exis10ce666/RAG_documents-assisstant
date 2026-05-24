import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";

const PREPARED_QUESTIONS = [
  {
    id: "must-2024-rule-mission",
    group: "ШУТИС-ийн дүрэм 2024",
    label: "2024 оны ШУТИС-ийн дүрэмд эрхэм зорилгыг юу гэж тодорхойлсон бэ?",
    question:
      "2024 оны ШУТИС-ийн дүрэмд ШУТИС-ийн эрхэм зорилгыг юу гэж тодорхойлсон бэ?",
    expectedAnswer:
      "2024 оны ШУТИС-ийн дүрэмд ШУТИС-ийн эрхэм зорилгыг 'Эх орны хөгжлийн гарцыг тодорхойлох хүн-байгальд ээлтэй шинжлэх ухаан, технологийн мэдлэг, инновацийг бүтээх авьяас чадварын төвлөрөл байна.' гэж тодорхойлсон.",
  },
  {
    id: "must-2024-rule-repeal",
    group: "ШУТИС-ийн дүрэм 2024",
    label: "2024 оны ШУТИС-ийн дүрэм батлагдсанаар өмнөх аль дүрмийг хүчингүй болсонд тооцсон бэ?",
    question: "2024 оны ШУТИС-ийн дүрэм батлагдсантай холбогдуулан өмнөх аль дүрмийг хүчингүй болсонд тооцсон бэ?",
    expectedAnswer:
      "Удирдах зөвлөлийн 2017 оны 05 дугаар сарын 16-ны өдрийн 11 тоот тогтоолоор батлагдсан 'ШУТИС-ийн дүрэм'-ийг хүчингүй болсонд тооцсон.",
  },
  {
    id: "must-student-2012-rule-start-date",
    group: "ШУТИС-ийн оюутны ёс зүйн дүрэм 2012",
    label: "2012 оны оюутны ёс зүйн дүрэм хэзээнээс мөрдөгдөх болсон бэ?",
    question:
      "ШУТИС-ийн оюутны ёс зүйн дүрэм хэзээнээс мөрдөгдөх болсон бэ?",
    expectedAnswer:
      "ШУТИС-ийн оюутны ёс зүйн дүрэм 2012 оны 10 дугаар сарын 10-ны өдрөөс эхлэн мөрдөгдөх болсон.",
  },
  {
    id: "must-student-2012-monitoring",
    group: "ШУТИС-ийн оюутны ёс зүйн дүрэм 2012",
    label: "Оюутны ёс зүйн дүрмийн биелэлтэд хэн хяналт тавихаар заасан бэ?",
    question:
      "2012 оны ШУТИС-ийн оюутны ёс зүйн дүрмийг мөрдөж, биелэлтэд нь хяналт тавьж ажиллахыг ямар албан тушаалтан, байгууллагуудад даалгасан бэ?",
    expectedAnswer:
      "Дүрмийн биелэлтэд хяналт тавьж ажиллахыг СБЗГ /Н.Ганзориг/, ЗХШҮГ /Ж.Арслан/, Оюутны холбоо /Б.Сайнсанаа/ болон бүрэлдэхүүн сургуулийн захирлуудад даалгасан.",
  },
  {
    id: "must-student-2012-violations",
    group: "ШУТИС-ийн оюутны ёс зүйн дүрэм 2012",
    label: "Ёс зүйн зөрчил ямар оюутанд тавигддаг вэ?",
    question:
      "ШУТИС-ийн оюутны ёс зүйн дүрэмд зааснаар ёс зүйн зөрчлийн гомдол, хүсэлтийг хүлээн авснаас хойш хэд хоногийн дотор шалгах бөгөөд ямар сахилгын шийтгэлүүд ногдуулдаг вэ?",
    expectedAnswer:
      "Гомдол хүсэлтийг хүлээн авсан өдрөөс хойш 14 хоногт багтаан шалгах бөгөөд нэмэлт материал шалгах шаардлагатай бол Зөвлөлийн дарга хугацааг 7 хүртэл хоногоор сунгана. Зөрчил гаргасан оюутанд амаар болон бичгээр сануулах, суралцах эрхийг хязгаарлах зэрэг сахилгын шийтгэл ногдуулна.",
  },
  
  {
    id: "labor-2016-working-hours-banking",
    group: "Ажиллах хүчний гадаад шилжих хөдөлгөөний судалгаа 2016",
    label: "БНСУ болон Япон дахь монголчуудын ажлын цаг, банк ашиглалтын харьцуулалт юу вэ?",
    question:
      "2016 оны судалгаагаар БНСУ болон Япон улсад ажиллаж, амьдарч буй монгол иргэдийн 7 хоногийн дундаж ажлын цаг болон мөнгөн гуйвуулга хийхдээ банкийг ашиглах хувь хэмжээ ямар байсан бэ?",
    expectedAnswer:
      "БНСУ-д ажиллаж буй иргэд 7 хоногт дунджаар 48.9 цаг ажилладаг бөгөөд 44.0 хувь нь банкаар мөнгөө шилжүүлдэг. Харин Япон улсад амьдарч буй иргэдийн 7 хоногийн дундаж ажлын цаг нь 31.4 байдаг бөгөөд зөвхөн 2.0 хувь нь банкаар мөнгөө шилжүүлдэг байна.",
  },
  {
    id: "nist-ai-rmf-goal",
    group: "NIST AI RMF 1.0",
    label: "What is the goal of the NIST AI RMF 1.0?",
    question: "What is the goal of the NIST AI RMF 1.0?",
    expectedAnswer:
      "The goal of the NIST AI RMF 1.0 is to help organizations designing, developing, deploying, or using AI systems manage AI risks and promote trustworthy and responsible development and use of AI systems.",
  },
  {
    id: "nist-ai-rmf-ai-system-definition",
    group: "NIST AI RMF 1.0",
    label: "How does the NIST AI RMF 1.0 define an AI system?",
    question: "How does the NIST AI RMF 1.0 define an AI system?",
    expectedAnswer:
      "The NIST AI RMF 1.0 defines an AI system as an engineered or machine-based system that can generate outputs such as predictions, recommendations, or decisions influencing real or virtual environments, for a given set of objectives, and can operate with varying levels of autonomy.",
  },
  {
    id: "nist-ai-rmf-core-functions",
    group: "NIST AI RMF 1.0",
    label: "What are the four AI RMF Core functions?",
    question: "What are the four core functions of the NIST AI RMF 1.0?",
    expectedAnswer:
      "The four core functions of the NIST AI RMF 1.0 are GOVERN, MAP, MEASURE, and MANAGE.",
  },
  {
    id: "nist-ai-rmf-trustworthy-ai",
    group: "NIST AI RMF 1.0",
    label: "What are the characteristics of trustworthy AI systems?",
    question:
      "What are the characteristics of trustworthy AI systems according to the NIST AI RMF 1.0?",
    expectedAnswer:
      "According to the NIST AI RMF 1.0, trustworthy AI systems are valid and reliable, safe, secure and resilient, accountable and transparent, explainable and interpretable, privacy-enhanced, and fair with harmful bias managed.",
  },
  {
    id: "nist-ai-rmf-risk-measurement-challenges",
    group: "NIST AI RMF 1.0",
    label: "Why is AI risk measurement challenging?",
    question:
      "Why is AI risk measurement challenging according to the NIST AI RMF 1.0?",
    expectedAnswer:
      "AI risk measurement is challenging because some AI risks or failures are not well-defined or adequately understood. The document also mentions challenges such as third-party software, hardware, and data, emergent risks, and lack of reliable metrics.",
  },
  {
    id: "nist-ai-rmf-govern-function",
    group: "NIST AI RMF 1.0",
    label: "What does the GOVERN function do?",
    question: "What does the GOVERN function do in the NIST AI RMF 1.0?",
    expectedAnswer:
      "The GOVERN function helps establish and maintain AI risk management culture, policies, processes, procedures, and organizational structures. It is designed to be a cross-cutting function that supports the other AI RMF functions.",
  },
  {
    id: "nist-ai-rmf-measure-function",
    group: "NIST AI RMF 1.0",
    label: "What does the MEASURE function do?",
    question: "What does the MEASURE function do in the NIST AI RMF 1.0?",
    expectedAnswer:
      "The MEASURE function uses quantitative, qualitative, or mixed-method tools and methodologies to analyze, assess, benchmark, and monitor AI risks and related impacts.",
  },
  {
    id: "nist-ai-rmf-explainability-interpretability",
    group: "NIST AI RMF 1.0",
    label: "What is the difference between explainability and interpretability?",
    question:
      "What is the difference between explainability and interpretability according to the NIST AI RMF 1.0?",
    expectedAnswer:
      "Explainability refers to a representation of the mechanisms behind AI system operation. Interpretability refers to the meaning of an AI system’s output in the context of its intended purpose.",
  },
  {
    id: "nist-ai-rmf-transparency-relation",
    group: "NIST AI RMF 1.0",
    label: "Does transparency guarantee other characteristics like accuracy or fairness?",
    question:
      "According to the NIST AI RMF 1.0, does a transparent AI system automatically guarantee that it is accurate, privacy-enhanced, secure, or fair?",
    expectedAnswer:
      "No. According to the document, a transparent system is not necessarily an accurate, privacy-enhanced, secure, or fair system, though it is difficult to determine whether an opaque system possesses such characteristics.",
  },
  {
    id: "hallucination-must-student-tuition",
    group: "Hallucination test",
    label: "2012 оны оюутны журамд 2026 оны сургалтын төлбөрийн хэмжээ бий юу?",
    question:
      "2012 оны ШУТИС-ийн оюутны дотоод журамд 2026 оны сургалтын төлбөрийн хэмжээг хэд гэж заасан бэ?",
    expectedAnswer:
      "I don't have enough information in the uploaded file to answer this.",
  },
  {
    id: "hallucination-must-2024-student-dorm-price",
    group: "Hallucination test",
    label: "2024 оны ШУТИС-ийн дүрэмд дотуур байрны үнэ бий юу?",
    question:
      "2024 оны ШУТИС-ийн дүрэмд оюутны дотуур байрны 2026 оны төлбөрийг хэд гэж заасан бэ?",
    expectedAnswer:
      "I don't have enough information in the uploaded file to answer this.",
  },
  {
    id: "hallucination-nist-mongolia-law",
    group: "Hallucination test",
    label: "What does the NIST AI RMF 1.0 say about Mongolia's AI law?",
    question: "What does the NIST AI RMF 1.0 say about Mongolia's AI law?",
    expectedAnswer:
      "I don't have enough information in the uploaded file to answer this.",
  },
];

function normalizeDoc(doc) {
  return {
    document_id: doc.document_id || doc.id,
    filename: doc.filename || doc.name || "Unknown PDF",
    pages: doc.pages || doc.page_count || 0,
    chunks: doc.chunks || doc.chunk_count || 0,
    extraction_methods: doc.extraction_methods || [],
  };
}

function formatScore(value) {
  if (typeof value === "number") return value.toFixed(4);
  if (!value) return "-";
  return value;
}

function chunkFileName(chunk) {
  return chunk.filename || chunk.source_file || chunk.file || "Unknown PDF";
}

function chunkSourceIndex(chunk, fallbackIndex) {
  return chunk.source_chunk_index || chunk.chunk_index || chunk.chunk_id || fallbackIndex;
}

export default function App() {
  const [documents, setDocuments] = useState([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [selectedDocument, setSelectedDocument] = useState(null);

  const [searchScope, setSearchScope] = useState("selected");
  const [forceOcr, setForceOcr] = useState(false);

  const [questionMode, setQuestionMode] = useState("prepared");
  const [selectedPreparedId, setSelectedPreparedId] = useState(PREPARED_QUESTIONS[0]?.id || "");
  const [file, setFile] = useState(null);
  const [question, setQuestion] = useState(PREPARED_QUESTIONS[0]?.question || "");
  const [result, setResult] = useState(null);

  const [loadingDocs, setLoadingDocs] = useState(false);
  const [loadingSelect, setLoadingSelect] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const questionCount = question.length;

  const selectedDocFromList = useMemo(() => {
    return documents.find((d) => d.document_id === selectedDocumentId) || null;
  }, [documents, selectedDocumentId]);

  const activeDocument = selectedDocument || selectedDocFromList;

  const selectedPreparedQuestion = useMemo(() => {
    return PREPARED_QUESTIONS.find((item) => item.id === selectedPreparedId) || PREPARED_QUESTIONS[0] || null;
  }, [selectedPreparedId]);

  const preparedGroups = useMemo(() => {
    const groups = {};
    for (const item of PREPARED_QUESTIONS) {
      if (!groups[item.group]) groups[item.group] = [];
      groups[item.group].push(item);
    }
    return groups;
  }, []);

  function switchQuestionMode(mode) {
    setQuestionMode(mode);
    setResult(null);
    setError("");
    setSuccess("");

    if (mode === "prepared" && selectedPreparedQuestion) {
      setQuestion(selectedPreparedQuestion.question);
    }

    if (mode === "custom") {
      setQuestion("");
    }
  }

  function handlePreparedQuestionChange(id) {
    setSelectedPreparedId(id);
    setResult(null);
    setError("");
    setSuccess("");

    const selected = PREPARED_QUESTIONS.find((item) => item.id === id);
    if (selected) setQuestion(selected.question);
  }

  async function fetchDocuments() {
    try {
      setLoadingDocs(true);
      setError("");

      const res = await axios.get(`${API_BASE}/documents`);
      const rawDocs = Array.isArray(res.data) ? res.data : res.data.documents || res.data.items || [];
      const normalized = rawDocs.map(normalizeDoc);
      setDocuments(normalized);

      if (normalized.length > 0 && !selectedDocumentId) {
        setSelectedDocumentId(normalized[0].document_id);
        setSelectedDocument(normalized[0]);
      }
    } catch (err) {
      const detail = err.response?.data?.detail || err.response?.data?.message || err.message || "Өмнө хадгалсан файлуудыг уншиж чадсангүй.";
      setError(`Өмнө хадгалсан файлуудыг уншиж чадсангүй: ${detail}`);
      console.error(err);
    } finally {
      setLoadingDocs(false);
    }
  }

  async function loadSelectedDocument(docId) {
    if (!docId) return;

    const doc = documents.find((d) => d.document_id === docId);
    setSelectedDocument(doc || null);
    setResult(null);
    setError("");
    setSuccess("");

    try {
      setLoadingSelect(true);
      await axios.post(`${API_BASE}/documents/${docId}/load`);
      setSuccess("Файл амжилттай сонгогдлоо.");
    } catch (err) {
      const detail = err.response?.data?.detail || err.response?.data?.message || err.message || "Файлыг сонгох үед index дахин үүсгэж чадсангүй.";
      setError(`Файлыг сонгох үед алдаа гарлаа: ${detail}`);
      console.error(err);
    } finally {
      setLoadingSelect(false);
    }
  }

  async function handleUpload() {
    if (!file) {
      setError("Эхлээд PDF файл сонгоно уу.");
      return;
    }

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Зөвхөн PDF файл upload хийнэ.");
      return;
    }

    try {
      setUploading(true);
      setError("");
      setSuccess("");
      setResult(null);

      const formData = new FormData();
      formData.append("file", file);

      const res = await axios.post(`${API_BASE}/upload?force_ocr=${forceOcr}`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const uploadedDoc = normalizeDoc(res.data);
      setSuccess("Шинэ PDF амжилттай upload хийгдлээ.");
      setFile(null);

      await fetchDocuments();

      setSelectedDocumentId(uploadedDoc.document_id);
      setSelectedDocument(uploadedDoc);
      setSearchScope("selected");
    } catch (err) {
      const detail = err.response?.data?.detail || err.response?.data?.message || err.message || "PDF upload хийх үед алдаа гарлаа.";
      setError(`PDF upload хийх үед алдаа гарлаа: ${detail}`);
      console.error(err);
    } finally {
      setUploading(false);
    }
  }

  async function askQuestion() {
    if (searchScope === "selected" && !selectedDocumentId) {
      setError("Эхлээд PDF файл сонгоно уу.");
      return;
    }

    if (!question.trim()) {
      setError("Асуултаа бичнэ үү.");
      return;
    }

    try {
      setAsking(true);
      setError("");
      setSuccess("");
      setResult(null);

      const res = await axios.post(`${API_BASE}/ask`, {
        document_id: searchScope === "selected" ? selectedDocumentId : null,
        question: question.trim(),
        search_scope: searchScope,
      });

      setResult(res.data);
    } catch (err) {
      const detail = err.response?.data?.detail || err.response?.data?.message || err.message || "Асуулт асуух үед алдаа гарлаа.";
      setError(`Асуулт асуух үед алдаа гарлаа: ${detail}`);
      console.error(err);
    } finally {
      setAsking(false);
    }
  }

  useEffect(() => {
    fetchDocuments();
  }, []);

  return (
    <div className="app-shell">
      <div className="bg-orb bg-orb-left" />
      <div className="bg-orb bg-orb-right" />
      <div className="dots dots-right" />
      <div className="dots dots-left" />

      <main className="app-container">
        <header className="hero">
          <div className="hero-title-row">
            <div className="hero-icon">▤</div>
            <h1>RAG Document Assistant</h1>
          </div>
          <p>
            Өмнө upload хийсэн PDF сонгох эсвэл бүх PDF дотроос хайгаад hybrid retrieval ашиглан асуулт асууна.
          </p>
        </header>

        {error && <div className="alert alert-error">{error}</div>}
        {success && <div className="alert alert-success">{success}</div>}

        <section className="card">
          <div className="section-heading">
            <div className="step-badge">1</div>
            <div className="section-icon">📁</div>
            <div>
              <h2>Файл сонгох</h2>
              <p>Нэг PDF дээр хайх эсвэл хадгалсан бүх PDF дотроос зэрэг хайж болно.</p>
            </div>
          </div>

          <div className="scope-toggle">
            <button className={`scope-btn ${searchScope === "selected" ? "active" : ""}`} onClick={() => setSearchScope("selected")} type="button">
              Сонгосон файл
            </button>
            <button className={`scope-btn ${searchScope === "all" ? "active" : ""}`} onClick={() => setSearchScope("all")} type="button">
              Бүх файл
            </button>
          </div>

          <div className="select-grid">
            <div className="left-panel">
              <label className="field-label">PDF файлаа сонгоно уу</label>
              <div className="control-row">
                <select
                  value={selectedDocumentId}
                  onChange={(e) => {
                    setSelectedDocumentId(e.target.value);
                    loadSelectedDocument(e.target.value);
                  }}
                  disabled={searchScope === "all" || loadingDocs || loadingSelect || documents.length === 0}
                >
                  {documents.length === 0 && <option value="">Хадгалсан PDF алга</option>}
                  {documents.map((doc) => (
                    <option key={doc.document_id} value={doc.document_id}>
                      {doc.filename} | {doc.pages} pages | {doc.chunks} chunks
                    </option>
                  ))}
                </select>
                <button className="secondary-btn" onClick={fetchDocuments} disabled={loadingDocs}>
                  ↻ {loadingDocs ? "Уншиж байна..." : "Шинэчлэх"}
                </button>
              </div>

              <div className="info-note">
                <div className="info-dot">i</div>
                <div>
                  <strong>{searchScope === "all" ? "Бүх файл дээр хайна" : "Сонгосон файл дээр хайна"}</strong>
                  <span>
                    {searchScope === "all"
                      ? `Одоогоор ${documents.length} PDF-ийн бүх chunk дотроос хайлт хийнэ.`
                      : "Доорх мэдээлэл нь сонгосон баримтын талаарх дэлгэрэнгүй мэдээлэл юм."}
                  </span>
                </div>
              </div>
            </div>

            <div className="doc-summary">
              <div className="doc-summary-title">
                <span className="doc-icon">{searchScope === "all" ? "🗂️" : "📄"}</span>
                <strong>{searchScope === "all" ? "Бүх хадгалсан PDF" : activeDocument?.filename || "Файл сонгоогүй"}</strong>
              </div>
              <div className="doc-row"><span>Search mode</span><b>{searchScope === "all" ? "All files" : "Selected file"}</b></div>
              <div className="doc-row"><span>Document ID</span><b>{searchScope === "all" ? "-" : activeDocument?.document_id || "-"}</b></div>
              <div className="doc-row"><span>Хуудас</span><b>{searchScope === "all" ? documents.reduce((sum, doc) => sum + Number(doc.pages), 0) : activeDocument?.pages || 0}</b></div>
              <div className="doc-row"><span>Chunk</span><b>{searchScope === "all" ? documents.reduce((sum, doc) => sum + Number(doc.chunks), 0) : activeDocument?.chunks || 0}</b></div>
              {searchScope === "selected" && activeDocument?.extraction_methods?.length > 0 && (
                <div className="doc-row"><span>Extraction</span><b>{activeDocument.extraction_methods.join(", ")}</b></div>
              )}
            </div>
          </div>
        </section>

        <section className="card">
          <div className="section-heading">
            <div className="step-badge">2</div>
            <div className="section-icon">☁️</div>
            <div>
              <h2>Шинэ PDF Upload</h2>
              <p>Хэрэгтэй файл жагсаалтад байхгүй бол эндээс шинэ PDF нэмнэ.</p>
            </div>
          </div>

          <div className="upload-zone">
            <div className="upload-cloud">☁</div>
            <h3>PDF файлаа чирч оруулна уу</h3>
            <p>эсвэл доорх товчийг дарж файл сонгоно уу</p>

            <div className="upload-actions">
              <label className="file-btn">
                📂 Файл сонгох
                <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} />
              </label>
              <button className="primary-btn" onClick={handleUpload} disabled={uploading}>
                {uploading ? "Upload хийж байна..." : "Upload хийх"}
              </button>
            </div>

            <label className="ocr-toggle">
              <input type="checkbox" checked={forceOcr} onChange={(e) => setForceOcr(e.target.checked)} />
              <span>OCR ашиглах <small>/ scanned эсвэл copy хийхэд үсэг эвдэрдэг PDF дээр асаана /</small></span>
            </label>

            <span className="file-name">{file ? file.name : "Зөвхөн PDF файл дэмжинэ."}</span>
          </div>
        </section>

        <section className="card">
          <div className="section-heading">
            <div className="step-badge">3</div>
            <div className="section-icon">💬</div>
            <div>
              <h2>Асуулт асуух</h2>
              <p>Бэлэн асуултаар шалгах эсвэл өөрийн асуултыг бичиж болно.</p>
            </div>
          </div>

          <div className="question-mode-toggle">
            <button type="button" className={`question-mode-btn ${questionMode === "prepared" ? "active" : ""}`} onClick={() => switchQuestionMode("prepared")}>Бэлэн асуулт</button>
            <button type="button" className={`question-mode-btn ${questionMode === "custom" ? "active" : ""}`} onClick={() => switchQuestionMode("custom")}>Өөрөө бичих</button>
          </div>

          {questionMode === "prepared" && (
            <div className="prepared-question-panel">
              <label className="field-label">Бэлэн асуулт сонгох</label>
              <select value={selectedPreparedId} onChange={(e) => handlePreparedQuestionChange(e.target.value)}>
                {Object.entries(preparedGroups).map(([groupName, items]) => (
                  <optgroup key={groupName} label={groupName}>
                    {items.map((item) => (
                      <option key={item.id} value={item.id}>{item.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>

              {selectedPreparedQuestion && (
                <div className="expected-answer-box">
                  <div className="expected-answer-header"><span>Expected answer</span><small>RAG хариулттай харьцуулна</small></div>
                  <p>{selectedPreparedQuestion.expectedAnswer}</p>
                </div>
              )}
            </div>
          )}

          {questionMode === "custom" && <div className="custom-question-note">Custom mode: хүссэн асуултаа өөрөө бичээд асууж болно.</div>}

          <textarea
            value={question}
            maxLength={2000}
            onChange={(e) => setQuestion(e.target.value)}
            readOnly={questionMode === "prepared"}
            placeholder="Жишээ: ШУТИС-ийн дүрэм хэзээнээс мөрдөгдөх болсон бэ?"
          />

          <div className="ask-footer">
            <span>{questionCount} / 2000</span>
            <button className="primary-btn ask-btn" onClick={askQuestion} disabled={asking}>✈ {asking ? "Уншиж байна..." : "Асуух"}</button>
          </div>
        </section>

        {result && (
          <section className="card result-card">
            <div className="section-heading">
              <div className="step-badge result-badge">✓</div>
              <div>
                <h2>Үр дүн</h2>
                <p>Hybrid retrieval болон RAG хариултын үр дүн.</p>
              </div>
            </div>

            {result.filename && (
              <div className="source-file">Best source file: <b>{result.filename}</b>{result.search_scope === "all" && " · searched across all files"}</div>
            )}

            <div className="answer-comparison-grid">
              <div className="answer-box"><h3>Final answer</h3><p>{result.answer || result.final_answer || "Хариулт алга."}</p></div>
              {questionMode === "prepared" && selectedPreparedQuestion && (
                <div className="answer-box expected-result-box"><h3>Expected answer</h3><p>{selectedPreparedQuestion.expectedAnswer}</p></div>
              )}
            </div>

            <div className="metric-grid">
              <div><span>Search scope</span><b>{result.search_scope || searchScope}</b></div>
              <div><span>Best page</span><b>{result.page || result.best_page || "-"}</b></div>
              <div><span>Best score</span><b>{formatScore(result.score || result.hybrid_score)}</b></div>
              <div><span>Document ID</span><b>{result.document_id || "-"}</b></div>
            </div>

            {Array.isArray(result.evidence_sentences || result.evidence) && (result.evidence_sentences || result.evidence).length > 0 && (
              <>
                <h3 className="subheading">Evidence sentences</h3>
                <div className="evidence-list">
                  {(result.evidence_sentences || result.evidence).map((item, index) => (
                    <div className="evidence-card" key={index}>
                      <div className="evidence-meta"><b>#{index + 1}</b>{item.filename && <span>File: {item.filename}</span>}<span>Хуудас: {item.page || "-"}</span><span>Score: {formatScore(item.score)}</span></div>
                      <p>{item.text || item.sentence || item}</p>
                    </div>
                  ))}
                </div>
              </>
            )}

            {Array.isArray(result.top_chunks) && result.top_chunks.length > 0 && (
              <>
                <h3 className="subheading">Top chunks</h3>
                <div className="chunk-list">
                  {result.top_chunks.map((chunk, index) => (
                    <details className="chunk-card" key={index}>
                      <summary>
                        <div className="chunk-summary-main"><b>Chunk #{index + 1}</b><span className="chunk-file-badge">📄 {chunkFileName(chunk)}</span></div>
                        <div className="chunk-source-grid">
                          <span><b>Original chunk:</b> {chunkSourceIndex(chunk, index + 1)}</span>
                          <span><b>Page:</b> {chunk.page || "-"}</span>
                          <span><b>Score:</b> {formatScore(chunk.score || chunk.hybrid_score || chunk.hybrid)}</span>
                          <span><b>Document ID:</b> {chunk.document_id || "-"}</span>
                        </div>
                      </summary>
                      <p>{chunk.text}</p>
                    </details>
                  ))}
                </div>
              </>
            )}
          </section>
        )}

        <footer className="footer-note">🛡 Таны файлууд локал орчинд хадгалагдана. Хувийн мэдээлэл гадагшлахгүй.</footer>
      </main>
    </div>
  );
}
