import React, { useEffect, useState } from "react";
import axios from "axios";
import AnalysisChart from "./analysisChart";

const API_BASE = "/api";

function App() {
  const [summary, setSummary] = useState({ buckets: [] });
  const [transactions, setTransactions] = useState([]);
  const [drilledTransactions, setDrilledTransactions] = useState([]);
  const [drillPath, setDrillPath] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [messages, setMessages] = useState([
    { id: 1, role: "assistant", text: "Welcome! Your loaded data is available for analysis." },
  ]);
  const [file, setFile] = useState(null);
  const [fileId, setFileId] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [input, setInput] = useState("");

  useEffect(() => {
    fetchSummary();
    fetchTransactions();
    fetchAnalysis();
  }, []);

  const fetchSummary = async () => {
    try {
      const response = await axios.get(`${API_BASE}/summary`);
      setSummary(response.data);
    } catch (error) {
      console.error(error);
    }
  };

  const fetchTransactions = async () => {
    try {
      const response = await axios.get(`${API_BASE}/transactions?limit=20`);
      setTransactions(response.data);
    } catch (error) {
      console.error(error);
    }
  };

  const fetchAnalysis = async () => {
    try {
      // request analysis for the past 30 days
      const end = new Date();
      const start = new Date();
      start.setDate(end.getDate() - 30);
      const startDate = start.toISOString().slice(0, 10);
      const endDate = end.toISOString().slice(0, 10);
      const response = await axios.get(`${API_BASE}/analysis`, { params: { start_date: startDate, end_date: endDate } });
      setAnalysis(response.data);
    } catch (error) {
      console.error(error);
    }
  };

  const fetchTransactionsForDrill = async (pathArray) => {
    // map path to filters: [account_type, bank, card_network, bucket]
    const filters = {};
    if (pathArray[0]) filters.account_type = pathArray[0];
    if (pathArray[1]) filters.bank = pathArray[1];
    if (pathArray[2]) filters.card_network = pathArray[2];
    if (pathArray[3]) filters.bucket = pathArray[3];
    const { startDate, endDate } = lastMonthRange();
    filters.start_date = startDate;
    filters.end_date = endDate;
    try {
      const resp = await axios.post(`${API_BASE}/transactions_filter`, filters);
      // above replace ensures correct path building in dev/prod
      const rows = resp.data;
      setDrilledTransactions(rows);
      setDrillPath(pathArray);
    } catch (err) {
      console.error('drill fetch failed', err);
      setDrilledTransactions([]);
    }
  };

  const lastMonthRange = () => {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 30);
    const startDate = start.toISOString().slice(0, 10);
    const endDate = end.toISOString().slice(0, 10);
    return { startDate, endDate };
  };

  const appendMessage = (role, text) => {
    setMessages((prev) => [...prev, { id: prev.length + 1, role, text }]);
  };

  const handleUpload = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);

    appendMessage("user", `Uploading ${file.name}...`);

    try {
      const response = await axios.post(`${API_BASE}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const { fileId: id, message } = response.data;
      setFileId(id);
      appendMessage("assistant", message);
      // If the uploaded file is parsed/identified, auto-process it via the chat endpoint
      if (response.data.parsed) {
        setProcessing(true);
        appendMessage("assistant", "Processing uploaded statement...");
        try {
          const proc = await axios.post(`${API_BASE}/chat`, { message: "process it now", fileId: id });
          appendMessage("assistant", proc.data.reply);
          if (proc.data.analysis) setAnalysis(proc.data.analysis);
        } catch (err) {
          appendMessage("assistant", "Processing failed. Try asking the assistant to process it.");
          console.error(err);
        } finally {
          setProcessing(false);
          fetchSummary();
          fetchTransactions();
          fetchAnalysis();
        }
      } else {
        fetchSummary();
        fetchAnalysis();
      }
    } catch (error) {
      appendMessage("assistant", "Upload failed. Please try again.");
      console.error(error);
    }
  };

  const handleFileSelected = (fileObj) => {
    setFile(fileObj);
  };

  const handleSend = async () => {
    // allow sending either text or an attached file
    if (!input.trim() && !file) return;

    // If a file is attached, upload it first and then trigger processing via chat
    if (file) {
      appendMessage("user", `Uploading ${file.name}...`);
      const formData = new FormData();
      formData.append("file", file);
      try {
        const up = await axios.post(`${API_BASE}/upload`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        const id = up.data.fileId;
        setFileId(id);
        appendMessage("assistant", up.data.message);

        // automatically process identified uploads
        setProcessing(true);
        appendMessage("assistant", "Processing uploaded statement...");
        try {
          const proc = await axios.post(`${API_BASE}/chat`, { message: "process it now", fileId: id });
          appendMessage("assistant", proc.data.reply);
          if (proc.data.analysis) setAnalysis(proc.data.analysis);
          if (proc.data.action === "processed") {
            fetchSummary();
            fetchTransactions();
          }
        } catch (err) {
          appendMessage("assistant", "Processing failed. Try asking the assistant to process it.");
          console.error(err);
        } finally {
          setProcessing(false);
        }
      } catch (err) {
        appendMessage("assistant", "Upload failed. Please try again.");
        console.error(err);
      }
      // clear attached file and input
      setFile(null);
      setInput("");
      return;
    }

    // otherwise try analysis query first (for prompts like "how much I spent in food_delivery")
    const { startDate, endDate } = lastMonthRange();
    try {
      const aq = await axios.post(`${API_BASE}/analysis_query`, { prompt: input, start_date: startDate, end_date: endDate });
      if (aq.data && aq.data.intent && aq.data.intent !== "unknown") {
        // show the analysis reply
        appendMessage("assistant", aq.data.message || "Here are the results.");
        if (aq.data.intent === "sunburst" && aq.data.data) {
          setAnalysis(aq.data.data);
        }
        if (aq.data.intent === "bucket_aggregate" && aq.data.rows) {
          // update chart by re-fetching analysis and show top-level summary
          setAnalysis(getAnalysisFromBucket(aq.data));
        }
        return;
      }
    } catch (err) {
      console.error("analysis_query failed", err);
    }

    // fall back to regular chat when analysis doesn't match
    appendMessage("user", input);
    const payload = { message: input, fileId };
    setInput("");
    // show processing status while waiting for assistant reply
    setProcessing(true);
    try {
      const response = await axios.post(`${API_BASE}/chat`, payload);
      appendMessage("assistant", response.data.reply);
      if (response.data.analysis) {
        setAnalysis(response.data.analysis);
      }
      if (response.data.action === "processed") {
        fetchSummary();
        fetchTransactions();
      }
    } catch (error) {
      appendMessage("assistant", "The chat service is unavailable right now.");
      console.error(error);
    } finally {
      setProcessing(false);
    }
  };

  const getAnalysisFromBucket = (agg) => {
    // create a minimal sunburst-like payload focused on the bucket
    return { name: 'root', children: [ { name: agg.bucket || 'bucket', children: [ { name: agg.bucket, children: [ { name: 'total', value: agg.total } ] } ] } ] };
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">Finance Agent</div>
        <div className="summary-text">View your existing monthly analytics now, and optionally upload statements for new processing.</div>
      </header>
      <main className="app-main">
        <section className="dashboard-panel">
          <div className="card chart-card">
            <AnalysisChart data={analysis} onDrill={fetchTransactionsForDrill} />
          </div>
          {drilledTransactions && drilledTransactions.length > 0 && (
            <div className="card transactions-card">
              <h2>Drill Transactions: {drillPath.join(' / ')}</h2>
              <div className="txn-list">
                {drilledTransactions.map((txn) => (
                  <div key={txn.id} className="txn-row">
                    <div>{txn.date}</div>
                    <div>{txn.description}</div>
                    <div>{txn.bucket || 'pending'}</div>
                    <div>{Number(txn.amount).toFixed(2)} {txn.currency}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
        <aside className="chat-panel">
          <div className="chat-header">
            <div>
              <h2>AI Assistant</h2>
              <p>Ask to process the uploaded statement or request a summary.</p>
            </div>
            <div className="chat-status">
              <strong>Status:</strong> {processing ? <span className="status-processing">Processing...</span> : <span className="status-idle">Idle</span>}
            </div>
          </div>
          <div className="chat-messages">
            {messages.map((message) => (
              <div key={message.id} className={`chat-bubble ${message.role}`}>
                {message.text}
              </div>
            ))}
          </div>
          <div className="chat-input-row">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message or attach a PDF..."
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
            />
            <input
              type="file"
              accept="application/pdf"
              onChange={(e) => handleFileSelected(e.target.files?.[0] || null)}
              style={{ marginLeft: 8 }}
            />
            <button className="primary-button" onClick={handleSend}>
              Send
            </button>
          </div>
        </aside>
      </main>
    </div>
  );
}

export default App;
