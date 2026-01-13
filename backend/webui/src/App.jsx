import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import DeviceDetail from './components/DeviceDetail';
import Gallery from './components/Gallery';
import Settings from './components/Settings';
import Memories from './components/Memories';

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/device/:deviceId" element={<DeviceDetail />} />
          <Route path="/gallery" element={<Gallery />} />
          <Route path="/memories" element={<Memories />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
