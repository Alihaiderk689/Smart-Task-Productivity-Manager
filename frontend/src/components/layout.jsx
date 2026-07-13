import { useEffect, useState } from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, CheckSquare, Tags, Calendar, LogOut, Menu, X, Sparkles, ChevronDown, ChevronRight } from 'lucide-react';
import { base44 } from '../api/base44Client';
import { statusConfig, colorBgMap, getCategoryColor } from '../lib/taskUtils';

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [categoriesExpanded, setCategoriesExpanded] = useState(false);
  const [expandedCategoryIds, setExpandedCategoryIds] = useState(() => new Set());
  const [categories, setCategories] = useState([]);
  const [tasks, setTasks] = useState([]);
  const location = useLocation();

  const navItems = [
    { label: 'Dashboard', path: '/', icon: LayoutDashboard },
    { label: 'Tasks', path: '/tasks', icon: CheckSquare },
    { label: 'Calendar', path: '/calendar', icon: Calendar },
  ];

  // Keep the sidebar's category/task tree fresh as the user navigates around the app.
  useEffect(() => {
    let cancelled = false;
    Promise.all([base44.entities.Category.list(), base44.entities.Task.list()])
      .then(([catData, taskData]) => {
        if (!cancelled) {
          setCategories(catData);
          setTasks(taskData);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [location.pathname]);

  const toggleCategory = (id) => {
    setExpandedCategoryIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const categoriesActive = location.pathname.startsWith('/categories');

  const handleLogout = async () => {
    await base44.auth.logout('/login');
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Mobile header */}
      <header className="lg:hidden fixed top-0 left-0 right-0 z-40 bg-white/80 backdrop-blur-md border-b border-slate-200 px-4 h-16 flex items-center justify-between">
        <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2 -ml-2 text-slate-600">
          {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-lg bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">TaskFlow</span>
        </div>
        <div className="w-8" />
      </header>

      {/* Sidebar */}
      <aside className={`fixed top-0 left-0 z-30 h-full w-64 bg-white border-r border-slate-200 transition-transform duration-300 lg:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="p-6 pb-24 h-full overflow-y-auto">
          <Link to="/" className="flex items-center gap-2.5 mb-10" onClick={() => setSidebarOpen(false)}>
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <span className="font-bold text-xl tracking-tight text-slate-900">TaskFlow</span>
          </Link>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
              return (
                <Link key={item.path} to={item.path} onClick={() => setSidebarOpen(false)}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${active ? 'bg-indigo-50 text-indigo-600' : 'text-slate-600 hover:bg-slate-50'}`}>
                  <Icon className="w-5 h-5" />
                  {item.label}
                </Link>
              );
            })}

            {/* Categories: expandable tree of category -> tasks */}
            <div>
              <div className={`flex items-center rounded-xl text-sm font-medium transition-all ${categoriesActive ? 'bg-indigo-50 text-indigo-600' : 'text-slate-600 hover:bg-slate-50'}`}>
                <Link to="/categories" onClick={() => setSidebarOpen(false)} className="flex items-center gap-3 px-3 py-2.5 flex-1 min-w-0">
                  <Tags className="w-5 h-5 shrink-0" />
                  <span className="truncate">Categories</span>
                </Link>
                <button
                  type="button"
                  onClick={() => setCategoriesExpanded((v) => !v)}
                  className="p-2 mr-1.5 rounded-lg hover:bg-slate-100 text-slate-400 shrink-0"
                  aria-label={categoriesExpanded ? 'Collapse categories' : 'Expand categories'}
                  aria-expanded={categoriesExpanded}
                >
                  {categoriesExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </button>
              </div>

              {categoriesExpanded && (
                <div className="mt-1 ml-4 pl-3 border-l border-slate-100 space-y-0.5">
                  {categories.filter((cat) => tasks.some((t) => t.category === cat.id)).length === 0 ? (
                    <p className="px-3 py-2 text-xs text-slate-400">No tasks yet</p>
                  ) : (
                    categories
                      .filter((cat) => tasks.some((t) => t.category === cat.id))
                      .map((cat) => {
                        const catTasks = tasks.filter((t) => t.category === cat.id);
                        const isCatExpanded = expandedCategoryIds.has(cat.id);
                        return (
                          <div key={cat.id}>
                            <button
                              type="button"
                              onClick={() => toggleCategory(cat.id)}
                              className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-50"
                            >
                              {isCatExpanded ? <ChevronDown className="w-3 h-3 shrink-0" /> : <ChevronRight className="w-3 h-3 shrink-0" />}
                              <span className={`w-2 h-2 rounded-full shrink-0 ${colorBgMap[getCategoryColor(cat.id)]}`} />
                              <span className="truncate flex-1 text-left">{cat.name}</span>
                              <span className="text-slate-400">{catTasks.length}</span>
                            </button>
                            {isCatExpanded && (
                              <div className="ml-5 mt-0.5 mb-1 space-y-0.5">
                                {catTasks.map((task) => {
                                  const st = statusConfig[task.status] || statusConfig.Pending;
                                  return (
                                    <Link
                                      key={task.id}
                                      to={`/tasks/${task.id}`}
                                      onClick={() => setSidebarOpen(false)}
                                      className="flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg text-xs text-slate-600 hover:bg-slate-50 hover:text-indigo-600"
                                    >
                                      <span className="truncate">{task.title}</span>
                                      <span className={`shrink-0 w-1.5 h-1.5 rounded-full ${st.dot}`} title={st.label} />
                                    </Link>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      })
                  )}
                </div>
              )}
            </div>
          </nav>
        </div>
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-slate-100 bg-white">
          <button onClick={handleLogout} className="flex items-center gap-3 px-3 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50 rounded-xl w-full transition-colors">
            <LogOut className="w-5 h-5" />
            Logout
          </button>
        </div>
      </aside>

      {sidebarOpen && <div className="lg:hidden fixed inset-0 z-20 bg-black/30" onClick={() => setSidebarOpen(false)} />}

      <main className="lg:ml-64 pt-16 lg:pt-0 min-h-screen">
        <Outlet />
      </main>
    </div>
  );
}