export default function Footer() {
  return (
    <footer className="footer">
      <div>© {new Date().getFullYear()} AppDef to ABL Converter</div>
      <div className="footer-links">
        <span>Help</span>
        <span>Documentation</span>
        <span>Support</span>
      </div>
    </footer>
  );
}