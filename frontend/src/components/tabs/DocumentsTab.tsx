import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { FileText, Image, Upload, Download, Eye, Search, Filter } from 'lucide-react';
import { Document } from '../../types/employee';

interface DocumentsTabProps {
  documents: Document[];
}

export function DocumentsTab({ documents }: DocumentsTabProps) {
  const getFileIcon = (type: string) => {
    if (type === 'pdf') return <FileText className="w-5 h-5 text-red-500" />;
    if (type === 'image') return <Image className="w-5 h-5 text-blue-500" />;
    return <FileText className="w-5 h-5 text-slate-500" />;
  };

  const documentsByCategory = {
    'Employment': documents.filter(d => d.name.includes('Contract') || d.name.includes('NDA')),
    'Performance': documents.filter(d => d.name.includes('Performance') || d.name.includes('Review')),
    'Tax & Finance': documents.filter(d => d.name.includes('Tax') || d.name.includes('W2')),
    'Certificates': documents.filter(d => d.name.includes('Certificate')),
  };

  return (
    <div className="space-y-6">
      {/* Upload & Search */}
      <Card>
        <div className="p-6">
          <div className="flex items-center gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input placeholder="Search documents..." className="pl-10" />
            </div>
            <Button variant="outline">
              <Filter className="w-4 h-4 mr-2" />
              Filter
            </Button>
            <Button>
              <Upload className="w-4 h-4 mr-2" />
              Upload Document
            </Button>
          </div>
        </div>
      </Card>

      {/* Document Stats */}
      <div className="grid grid-cols-4 gap-6">
        <Card>
          <div className="p-6">
            <div className="text-slate-600 mb-2">Total Documents</div>
            <div className="text-slate-900">{documents.length}</div>
          </div>
        </Card>
        <Card>
          <div className="p-6">
            <div className="text-slate-600 mb-2">Employment</div>
            <div className="text-slate-900">{documentsByCategory['Employment'].length}</div>
          </div>
        </Card>
        <Card>
          <div className="p-6">
            <div className="text-slate-600 mb-2">Certificates</div>
            <div className="text-slate-900">{documentsByCategory['Certificates'].length}</div>
          </div>
        </Card>
        <Card>
          <div className="p-6">
            <div className="text-slate-600 mb-2">Tax Documents</div>
            <div className="text-slate-900">{documentsByCategory['Tax & Finance'].length}</div>
          </div>
        </Card>
      </div>

      {/* Documents by Category */}
      {Object.entries(documentsByCategory).map(([category, docs]) => (
        docs.length > 0 && (
          <Card key={category}>
            <div className="p-6">
              <h3 className="text-slate-900 mb-4">{category}</h3>
              
              <div className="space-y-2">
                {docs.map((doc) => (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between p-4 bg-slate-50 border border-slate-200 rounded-lg hover:border-blue-300 hover:shadow-sm transition-all"
                  >
                    <div className="flex items-center gap-4 flex-1">
                      <div className="w-10 h-10 bg-white border border-slate-200 rounded-lg flex items-center justify-center">
                        {getFileIcon(doc.type)}
                      </div>
                      <div className="flex-1">
                        <div className="text-slate-900">{doc.name}</div>
                        <div className="text-slate-500 flex items-center gap-3 mt-1">
                          <span>{doc.size}</span>
                          <span>·</span>
                          <span>Uploaded {new Date(doc.uploadDate).toLocaleDateString()}</span>
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" size="sm">
                        <Eye className="w-4 h-4" />
                      </Button>
                      <Button variant="ghost" size="sm">
                        <Download className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        )
      ))}

      {/* Recent Activity */}
      <Card>
        <div className="p-6">
          <h3 className="text-slate-900 mb-4">Recent Activity</h3>
          
          <div className="space-y-3">
            <div className="flex items-start gap-3 pb-3 border-b border-slate-200">
              <div className="w-2 h-2 bg-blue-500 rounded-full mt-2"></div>
              <div className="flex-1">
                <div className="text-slate-900">Performance_Review_Q3_2024.pdf uploaded</div>
                <div className="text-slate-500">October 1, 2024</div>
              </div>
            </div>
            <div className="flex items-start gap-3 pb-3 border-b border-slate-200">
              <div className="w-2 h-2 bg-green-500 rounded-full mt-2"></div>
              <div className="flex-1">
                <div className="text-slate-900">Certificate_UX_Design.pdf uploaded</div>
                <div className="text-slate-500">August 15, 2024</div>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-2 h-2 bg-purple-500 rounded-full mt-2"></div>
              <div className="flex-1">
                <div className="text-slate-900">Tax_Form_W2_2023.pdf uploaded</div>
                <div className="text-slate-500">January 31, 2024</div>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
